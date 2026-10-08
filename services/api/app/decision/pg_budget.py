"""PostgreSQL'de KALICI ve ATOMİK bütçe: canlı demo gibi ürün akışındaki ücretli çağrılar için.

Dosya tabanlı defterin (`budget_ledger.py`, değerlendirme deneyleri) yerine geçmez; ondan
bağımsızdır (eski `ilk-deneme` bakiyesi buraya aktarılmış sayılmaz). Ücretsiz bir sunucunun yerel
dosyası kalıcı değildir ve birden çok süreç aynı dosyayı güvenle yazamaz; bu yüzden durum
veritabanındadır.

Yöntem (her çağrıdan ve izin verilen her retry'dan ÖNCE):
1. İşlem açılır, bütçe satırı `FOR UPDATE` ile kilitlenir: aynı bütçeye aynı anda gelen tüm
   rezervasyonlar (eşzamanlı istekler, birden çok süreç) sırayla ve TEK TEK değerlendirilir.
2. Taahhüt edilen toplam hesaplanır: kesinleşmiş kayıtların ücreti + bekleyen (`pending`)
   kayıtların rezerve edilen en kötü durum tutarı.
3. `taahhüt + yeni rezervasyon > sınır` ise `BudgetExhausted` (istek HİÇ gönderilmez); değilse
   `pending` satır yazılır ve İŞLEM COMMIT EDİLİR. Sağlayıcıya ancak commit'ten sonra gidilir.

Çağrı bitince `settle` aynı satırı kesinleştirir: gerçek ücret biliniyorsa o (`known=True`), değilse
rezerve edilen en kötü durum bedeli (`known=False`, muhafazakâr). Süreç çağrı ile `settle` arasında
ölürse satır `pending` KALIR ve çözülmemiş rezervasyon olarak en kötü bedelle sayılmaya devam eder:
hiçbir zaman sıfır harcama sayılmaz. `settle` veritabanı hatasıyla başarısız olursa da satır
`pending` kalır (güvenli yön); sonuç yine de kullanıcıya döner, hata günlüğe yazılır.

Garanti edilemeyenler (`budget.py` başlığındakilere ek): Jev'de idempotency anahtarı ve "başarısız
istek faturalanır mı" belgelenmemiştir; bu yüzden belirsiz çağrılar en kötü bedelle sayılır ama
sağlayıcı faturasıyla birebir örtüşme garanti edilmez. Fiyat tablosu tarihlidir.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.decision.budget import Reservation
from app.decision.contract import BudgetExhausted
from app.decision.pricing import PriceEntry
from app.models import Budget, BudgetEntry

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


def price_version_text(price: PriceEntry | None, *, max_attempts: int = 1) -> str:
    """Hesaplamanın dayandığı fiyat ve varsayımlar (bütçe satırına yazılır)."""
    if price is None:
        return "fiyat bilinmiyor"
    return (
        f"{price.model} · {price.input_usd_per_mtok} USD/1M girdi, "
        f"{price.output_usd_per_mtok} USD/1M çıktı · kaynak {price.source_url} · "
        f"kontrol {price.checked_on.isoformat()} · üst sınır: istek gövdesi bayt sayısı ≥ token, "
        f"deneme hakkı {max_attempts}"
    )[:300]


def committed_usd(db: Session, budget_id: str) -> Decimal:
    """Taahhüt edilmiş toplam: kesinleşmiş ücretler + bekleyen rezervasyonların en kötü tutarı."""
    total = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (BudgetEntry.state == "settled", BudgetEntry.charge_usd),
                        else_=BudgetEntry.reserved_usd,
                    )
                ),
                0,
            )
        ).where(BudgetEntry.budget_id == budget_id)
    )
    return Decimal(total)


@dataclass(frozen=True)
class BudgetStatus:
    budget_id: str
    cap_usd: Decimal
    known_usd: Decimal  # sağlayıcı kullanımından hesaplanan GERÇEK harcama
    conservative_usd: Decimal  # bilinemediği için en kötü bedelle sayılan (gerçek olmayabilir)
    unresolved_usd: Decimal  # henüz kesinleşmemiş (uçuşta veya çöken süreçten kalan) rezervasyon
    remaining_usd: Decimal
    entries: int
    pending_entries: int
    bound_violations: int
    price_versions: tuple[str, ...]


def status(db: Session, budget_id: str) -> BudgetStatus | None:
    budget = db.get(Budget, budget_id)
    if budget is None:
        return None
    rows = db.execute(
        select(
            BudgetEntry.state,
            BudgetEntry.known,
            func.coalesce(func.sum(BudgetEntry.charge_usd), 0),
            func.coalesce(func.sum(BudgetEntry.reserved_usd), 0),
            func.count(),
        )
        .where(BudgetEntry.budget_id == budget_id)
        .group_by(BudgetEntry.state, BudgetEntry.known)
    ).all()
    known = conservative = unresolved = Decimal(0)
    entries = pending = 0
    for state, is_known, charged, reserved, count in rows:
        entries += count
        if state == "pending":
            unresolved += Decimal(reserved)
            pending += count
        elif is_known:
            known += Decimal(charged)
        else:
            conservative += Decimal(charged)
    violations = (
        db.scalar(
            select(func.count()).where(
                BudgetEntry.budget_id == budget_id, BudgetEntry.exceeded_reservation.is_(True)
            )
        )
        or 0
    )
    versions = tuple(
        db.scalars(
            select(BudgetEntry.price_version)
            .where(BudgetEntry.budget_id == budget_id)
            .distinct()
            .order_by(BudgetEntry.price_version)
        ).all()
    )
    return BudgetStatus(
        budget_id=budget_id,
        cap_usd=budget.cap_usd,
        known_usd=known,
        conservative_usd=conservative,
        unresolved_usd=unresolved,
        remaining_usd=budget.cap_usd - known - conservative - unresolved,
        entries=entries,
        pending_entries=pending,
        bound_violations=violations,
        price_versions=versions,
    )


class PgBudgetGuard:
    """`BudgetGuard` ile aynı `reserve`/`settle` arayüzü (BudgetedProvider bunu kullanır); durum
    PostgreSQL'dedir. Her işlem kendi kısa oturumunda yapılır: sağlayıcı çağrısı sırasında hiçbir
    veritabanı bağlantısı veya kilit tutulmaz."""

    records_usage = True  # BudgetedProvider: kullanım (token) bilgisini de `settle`a geçir

    def __init__(
        self,
        session_factory: SessionFactory,
        budget_id: str,
        *,
        job_id: UUID | None,
        price: PriceEntry | None,
        max_attempts: int = 1,
    ) -> None:
        self._session_factory = session_factory
        self.budget_id = budget_id
        self._job_id = job_id
        self._price_version = price_version_text(price, max_attempts=max_attempts)

    def reserve(self, amount: Decimal, *, provider: str = "", model: str = "") -> Reservation:
        if amount <= 0:
            raise BudgetExhausted("Rezervasyon tutarı pozitif olmalı.")
        with self._session_factory() as db:
            budget = db.scalar(select(Budget).where(Budget.id == self.budget_id).with_for_update())
            if budget is None:
                # Bütçe tanımlı değilse ücretli çağrı yapılmaz (açık olmayan = kapalı).
                raise BudgetExhausted(f"Bütçe kapsamı tanımlı değil: {self.budget_id!r}.")
            committed = committed_usd(db, self.budget_id)
            if committed + amount > budget.cap_usd:
                raise BudgetExhausted(
                    f"Harcama sınırı: {amount:.6f} USD rezerve edilemez "
                    f"(kalan {budget.cap_usd - committed:.6f})."
                )
            entry = BudgetEntry(
                budget_id=self.budget_id,
                job_id=self._job_id,
                provider=provider[:50],
                model=model[:100],
                price_version=self._price_version,
                reserved_usd=amount,
                state="pending",
            )
            db.add(entry)
            db.flush()
            entry_id = entry.id
            db.commit()  # İstek ancak bu commit'ten SONRA gönderilir.
        return Reservation(amount, entry_id)

    def settle(
        self,
        reservation: Reservation,
        actual: Decimal | None,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        known = actual is not None
        charge = actual if actual is not None else reservation.amount
        try:
            with self._session_factory() as db:
                db.execute(
                    update(BudgetEntry)
                    .where(BudgetEntry.id == reservation.seq, BudgetEntry.state == "pending")
                    .values(
                        state="settled",
                        charge_usd=charge,
                        known=known,
                        exceeded_reservation=bool(known and charge > reservation.amount),
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        settled_at=func.now(),
                    )
                )
                db.commit()
        except SQLAlchemyError:
            # Satır `pending` kalır = en kötü bedelle sayılmaya devam eder (güvenli yön). Sonuç
            # kullanıcıya yine döner; yalnızca hata türü günlüğe yazılır.
            logger.error(
                "Bütçe satırı kesinleştirilemedi (id=%s); rezervasyon çözülmemiş sayılacak.",
                reservation.seq,
            )
