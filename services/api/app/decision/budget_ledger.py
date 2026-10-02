"""Süreçler arası KALICI bütçe defteri.

Toplam harcama sınırı tek bir çalıştırmanın değil, aynı `budget_id` altındaki TÜM çalıştırmaların
toplamıdır. Bu yüzden harcama bellekte değil diskte tutulur:

- Her sağlayıcı çağrısından ÖNCE rezervasyon satırı diske yazılır (`begin`, fsync). Süreç çağrı
  sırasında çökerse satır `pending` kalır; sonraki çalıştırma onu "çözülmemiş rezervasyon" olarak
  en kötü durum bedeliyle bütçeden DÜŞER (gerçekte harcanıp harcanmadığı bilinemez).
- Çağrı bitince satır kesinleşir (`settle`): gerçek ücret (`known=true`) ya da bilinemediği için en
  kötü durum bedeli (`known=false`).
- Sınır deftere ilk açılışta yazılır; sonra farklı bir sınırla açmak REDDEDİLİR (kendiliğinden
  artırma/azaltma yok). Sınırı değiştirmek bilinçli, elle bir iştir.
- Aynı anda yalnızca bir süreç yazabilir: kilit dosyası (`.lock`). Çöken bir süreç kilidi
  bırakabilir; kilit OTOMATİK silinmez, kullanıcıya bildirilir (çalışan süreç olmadığı
  doğrulanınca elle silinir).
- Yazma atomiktir (geçici dosya + os.replace); kısmi dosya okunmaz.

Defterde anahtar, istek veya yanıt metni YOKTUR; yalnızca tutarlar, sağlayıcı/model adları ve
zaman damgaları.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

LEDGER_VERSION = 1


class LedgerError(RuntimeError):
    """Bütçe defteri kullanılamıyor."""


class LedgerLocked(LedgerError):
    """Defter başka bir süreç tarafından kullanılıyor (veya çöken bir süreç kilidi bıraktı)."""


class LedgerCapMismatch(LedgerError):
    """Defter başka bir toplam sınırla açılmış; sınır kendiliğinden değiştirilmez."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class LedgerEntry:
    seq: int
    run_id: str
    provider: str
    model: str
    reserved_usd: Decimal
    state: str  # "pending" | "settled"
    reserved_at: str
    charge_usd: Decimal | None = None
    known: bool | None = (
        None  # True: sağlayıcı kullanımından hesaplandı; False: en kötü durum bedeli
    )
    settled_at: str | None = None

    def to_json(self) -> dict:
        return {
            "seq": self.seq,
            "run_id": self.run_id,
            "provider": self.provider,
            "model": self.model,
            "reserved_usd": str(self.reserved_usd),
            "state": self.state,
            "reserved_at": self.reserved_at,
            "charge_usd": None if self.charge_usd is None else str(self.charge_usd),
            "known": self.known,
            "settled_at": self.settled_at,
        }

    @classmethod
    def from_json(cls, row: dict) -> "LedgerEntry":
        return cls(
            seq=row["seq"],
            run_id=row["run_id"],
            provider=row["provider"],
            model=row["model"],
            reserved_usd=Decimal(row["reserved_usd"]),
            state=row["state"],
            reserved_at=row["reserved_at"],
            charge_usd=None if row.get("charge_usd") is None else Decimal(row["charge_usd"]),
            known=row.get("known"),
            settled_at=row.get("settled_at"),
        )


class BudgetLedger:
    def __init__(self, path: Path, budget_id: str, cap: Decimal, created_at: str):
        self.path = path
        self.budget_id = budget_id
        self.cap = cap
        self.created_at = created_at
        self.entries: list[LedgerEntry] = []
        self._lock_path: Path | None = None

    # --- açma / kilit ---

    @classmethod
    def read(cls, path: Path) -> "BudgetLedger":
        """Salt okunur (kilitsiz) açılış: durum göstermek için."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise LedgerError(f"Bütçe defteri yok: {path}") from None
        except (OSError, ValueError) as exc:
            raise LedgerError(f"Bütçe defteri okunamadı ({type(exc).__name__}): {path}") from None
        ledger = cls(path, data["budget_id"], Decimal(data["cap_usd"]), data["created_at"])
        ledger.entries = [LedgerEntry.from_json(row) for row in data["entries"]]
        return ledger

    @classmethod
    def open(cls, path: Path, *, budget_id: str, cap: Decimal | None) -> "BudgetLedger":
        """Kilitleyerek açar (çalıştırma için). Yoksa `cap` ile oluşturur; varsa ve `cap` farklıysa
        reddeder."""
        lock = path.with_suffix(".lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                holder = json.loads(lock.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                holder = {}
            raise LedgerLocked(
                f"Bütçe defteri kilitli ({lock}; süreç {holder.get('pid', '?')}, "
                f"{holder.get('since', '?')}). Başka bir çalıştırma sürüyor olabilir ya da bir "
                "öncekinin çökmesiyle kilit kalmış olabilir. Çalışan bir süreç olmadığını "
                "doğrulamadan kilidi SİLME; doğruladıktan sonra elle silip tekrar dene."
            ) from None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "since": _now()}, handle)
        try:
            if path.exists():
                ledger = cls.read(path)
                if ledger.budget_id != budget_id:
                    raise LedgerError(
                        f"Defter kimliği uyuşmuyor: dosya {ledger.budget_id!r}, "
                        f"istenen {budget_id!r}."
                    )
                if cap is not None and cap != ledger.cap:
                    raise LedgerCapMismatch(
                        f"Bütçe defteri {ledger.cap} USD toplam sınırla açılmış; "
                        f"{cap} USD verildi. "
                        "Sınır kendiliğinden değiştirilmez: artırmak/azaltmak bilinçli ve elle "
                        f"yapılmalı ({path})."
                    )
            else:
                if cap is None or cap <= 0:
                    raise LedgerError("Yeni bütçe defteri için pozitif bir toplam sınır gerekir.")
                ledger = cls(path, budget_id, cap, _now())
                ledger._persist()
            ledger._lock_path = lock
            return ledger
        except BaseException:
            lock.unlink(missing_ok=True)
            raise

    def release(self) -> None:
        if self._lock_path is not None:
            self._lock_path.unlink(missing_ok=True)
            self._lock_path = None

    # --- toplamlar ---

    def settled_total(self) -> Decimal:
        return sum(
            (e.charge_usd or Decimal(0) for e in self.entries if e.state == "settled"), Decimal(0)
        )

    def settled_known_total(self) -> Decimal:
        return sum(
            (e.charge_usd or Decimal(0) for e in self.entries if e.state == "settled" and e.known),
            Decimal(0),
        )

    def pending_total(self) -> Decimal:
        return sum((e.reserved_usd for e in self.entries if e.state == "pending"), Decimal(0))

    def status(self) -> dict:
        settled = self.settled_total()
        known = self.settled_known_total()
        pending = self.pending_total()
        return {
            "budget_id": self.budget_id,
            "cap_usd": str(self.cap),
            "settled_total_usd": str(settled),
            "settled_known_usd": str(known),
            "settled_conservative_usd": str(settled - known),
            "unresolved_reserved_usd": str(pending),
            "remaining_usd": str(self.cap - settled - pending),
            "entries": len(self.entries),
            "pending_entries": sum(1 for e in self.entries if e.state == "pending"),
            "created_at": self.created_at,
        }

    # --- yazma (her biri diske atomik ve fsync'li) ---

    def begin(self, run_id: str, provider: str, model: str, reserved: Decimal) -> int:
        """Çağrıdan ÖNCE çağrılır; kalıcı olarak yazılmadan istek gönderilmez."""
        seq = len(self.entries) + 1
        self.entries.append(LedgerEntry(seq, run_id, provider, model, reserved, "pending", _now()))
        try:
            self._persist()
        except BaseException:
            self.entries.pop()
            raise
        return seq

    def settle(self, seq: int, charge: Decimal, known: bool) -> None:
        entry = self.entries[seq - 1]
        entry.state = "settled"
        entry.charge_usd = charge
        entry.known = known
        entry.settled_at = _now()
        self._persist()

    def _persist(self) -> None:
        payload = {
            "version": LEDGER_VERSION,
            "budget_id": self.budget_id,
            "cap_usd": str(self.cap),
            "created_at": self.created_at,
            "entries": [entry.to_json() for entry in self.entries],
        }
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
