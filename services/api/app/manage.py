"""Sunucuda çalıştırılan yönetim komutları (HTTP ucu değildir; yalnızca veritabanına erişimi olan
operatör kullanır).

Üretimde demo verisi yüklenmez (`app.seed` reddeder), bu yüzden ilk yönetici buradan oluşturulur:

  python -m app.manage create-admin --username ad.soyad --display-name "Ad Soyad"
  python -m app.manage reset-password --username ad.soyad

Parola komut satırı argümanı OLARAK VERİLMEZ (kabuk geçmişine ve süreç listesine girer):
etkileşimli olarak iki kez sorulur ya da `--password-stdin` ile standart girdiden bir satır
okunur. Parola hiçbir yere yazdırılmaz. Parola değişince o hesabın mevcut oturum belirteçleri
geçersiz olur.

Canlı demo (portföy demosu) için:

  python -m app.manage create-budget --id canli-demo --cap-usd 0.25 --purpose "Canlı demo"
  python -m app.manage budget-status --id canli-demo
  python -m app.manage purge-demo           # süresi dolan ziyaretçi hesaplarını ve taleplerini sil
  python -m app.manage export-demo-data     # kayıtlı deney sonuçlarını statik JSON'a aktar

`create-budget` ONAYLANMIŞ toplam sınırı tanımlar; aynı kapsam başka bir tutarla yeniden
tanımlanamaz (otomatik yenileme/artırma yoktur: yeni tutar bilinçli, yeni bir kapsam kimliğidir).
"""

import argparse
import getpass
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.decision import pg_budget
from app.domain.vocabulary import Role
from app.errors import AppError
from app.models import Budget, User
from app.schemas import UserCreate
from app.security import hash_password
from app.services import accounts

# Yönetici parolası için, genel kullanıcı kuralından (8) daha sıkı alt sınır.
MIN_ADMIN_PASSWORD_LENGTH = 12
# Yanlış yazılmış (ör. fazladan sıfır) bir tutarın canlıya yansımasını önleyen makul üst sınır.
MAX_BUDGET_USD = Decimal("100")
BUDGET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,58}$")


class CommandError(Exception):
    """Operatöre gösterilecek, beklenen bir hata (yığın izi basılmaz)."""


def _check_password(password: str) -> None:
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise CommandError(f"Parola en az {MIN_ADMIN_PASSWORD_LENGTH} karakter olmalı.")
    if len(password) > 128:
        raise CommandError("Parola en çok 128 karakter olabilir.")


def create_admin(db: Session, username: str, display_name: str, password: str) -> User:
    _check_password(password)
    try:
        data = UserCreate(
            username=username, display_name=display_name, password=password, role=Role.ADMIN
        )
    except ValidationError as exc:
        fields = ", ".join(str(error["loc"][0]) for error in exc.errors())
        raise CommandError(f"Geçersiz değer: {fields}.") from None
    try:
        return accounts.create_user(db, data)
    except AppError as exc:
        raise CommandError(exc.message) from None


def reset_password(db: Session, username: str, password: str) -> User:
    _check_password(password)
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        raise CommandError("Bu kullanıcı adıyla bir hesap yok.")
    user.password_hash = hash_password(password)
    db.commit()
    return user


def create_budget(db: Session, budget_id: str, cap: Decimal, purpose: str) -> tuple[Budget, bool]:
    """Bütçe kapsamını tanımlar. Aynı kimlik AYNI sınırla tekrar verilirse değişiklik yapmaz;
    farklı sınırla reddedilir (sınır kendiliğinden artırılmaz/azaltılmaz). (kapsam, yeni_mi)."""
    if not BUDGET_ID_RE.match(budget_id):
        raise CommandError(
            "Bütçe kimliği küçük harf, rakam, '.', '_' veya '-' içermeli (2–59 karakter)."
        )
    if not cap.is_finite() or cap <= 0:
        raise CommandError("Toplam sınır pozitif bir USD tutarı olmalı.")
    if cap > MAX_BUDGET_USD:
        raise CommandError(
            f"Toplam sınır {MAX_BUDGET_USD} USD'yi aşıyor; yazım hatası olabilir. Bilerek bu kadar "
            "yüksek bir sınır gerekiyorsa önce kodu ve belgeyi güncelle."
        )
    existing = db.get(Budget, budget_id)
    if existing is not None:
        if existing.cap_usd != cap:
            raise CommandError(
                f"{budget_id!r} zaten {_usd(existing.cap_usd)} USD sınırla tanımlı. Sınır "
                "kendiliğinden değiştirilmez; yeni bir tutar için yeni bir kapsam kimliği kullan."
            )
        return existing, False
    budget = Budget(id=budget_id, cap_usd=cap, purpose=purpose[:200])
    db.add(budget)
    db.commit()
    return budget, True


def _usd(value: Decimal) -> str:
    """Veritabanı hassasiyetindeki (0.2500000000) tutarı okunur yazar (0.25)."""
    return format(value.normalize(), "f")


def budget_report(db: Session, budget_id: str) -> str:
    st = pg_budget.status(db, budget_id)
    if st is None:
        raise CommandError(f"Bütçe kapsamı tanımlı değil: {budget_id!r}.")
    lines = [
        f"bütçe: {st.budget_id}",
        f"toplam sınır (onaylı):          {_usd(st.cap_usd)} USD",
        f"bilinen gerçek harcama:          {_usd(st.known_usd)} USD  (sağlayıcı kullanımından)",
        f"muhafazakâr (bilinemeyen):       {_usd(st.conservative_usd)} USD  (en kötü bedel)",
        f"çözülmemiş rezervasyon:          {_usd(st.unresolved_usd)} USD  (kesinleşmemiş)",
        f"kalan:                           {_usd(st.remaining_usd)} USD",
        f"kayıt: {st.entries} (bekleyen {st.pending_entries}); "
        f"üst sınır aşımı: {st.bound_violations}",
    ]
    lines += [f"fiyat/varsayım sürümü: {version}" for version in st.price_versions]
    return "\n".join(lines)


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Parola: ")
    if first != getpass.getpass("Parola (tekrar): "):
        raise CommandError("İki parola aynı değil.")
    return first


def _parse_usd(raw: str) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise CommandError(f"Geçersiz tutar: {raw!r}.") from None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.manage", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-admin", help="Yeni yönetici hesabı oluştur")
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", required=True)
    create.add_argument("--password-stdin", action="store_true", help="Parolayı stdin'den oku")

    reset = commands.add_parser("reset-password", help="Var olan hesabın parolasını değiştir")
    reset.add_argument("--username", required=True)
    reset.add_argument("--password-stdin", action="store_true", help="Parolayı stdin'den oku")

    budget = commands.add_parser("create-budget", help="Onaylanmış toplam bütçe kapsamını tanımla")
    budget.add_argument("--id", required=True, dest="budget_id")
    budget.add_argument("--cap-usd", required=True, help="Toplam sınır (USD), ör. 0.25")
    budget.add_argument("--purpose", default="")

    status = commands.add_parser("budget-status", help="Bütçe kapsamının durumunu göster")
    status.add_argument("--id", required=True, dest="budget_id")

    commands.add_parser("purge-demo", help="Süresi dolan ziyaretçi hesaplarını ve taleplerini sil")

    export = commands.add_parser(
        "export-demo-data", help="Kayıtlı deney sonuçlarını statik JSON olarak dışa aktar"
    )
    export.add_argument("--runs-dir", type=Path, default=None)
    export.add_argument("--out", type=Path, default=None)
    return parser


def _run(args: argparse.Namespace) -> None:
    if args.command == "export-demo-data":
        from app.export_demo import export_demo_data

        written = export_demo_data(args.runs_dir, args.out)
        print(f"{len(written)} dosya yazıldı: " + ", ".join(path.name for path in written))
        return
    if args.command in ("create-admin", "reset-password"):
        password = _read_password(args.password_stdin)
    with Session(get_engine()) as db:
        if args.command == "create-admin":
            user = create_admin(db, args.username, args.display_name, password)
            print(f"Yönetici oluşturuldu: {user.username}")
        elif args.command == "reset-password":
            user = reset_password(db, args.username, password)
            print(f"Parola değiştirildi: {user.username} (eski oturumları geçersiz oldu).")
        elif args.command == "create-budget":
            budget, created = create_budget(
                db, args.budget_id, _parse_usd(args.cap_usd), args.purpose
            )
            verb = "oluşturuldu" if created else "zaten tanımlı (değişiklik yok)"
            print(f"Bütçe {verb}: {budget.id} · toplam sınır {_usd(budget.cap_usd)} USD")
        elif args.command == "budget-status":
            print(budget_report(db, args.budget_id))
        elif args.command == "purge-demo":
            from app.services import demo

            total = 0
            while True:  # sınırlı partilerle, bitene dek
                count = demo.purge_expired(db, get_settings(), datetime.now(UTC))
                total += count
                if count < demo.PURGE_BATCH:
                    break
            print(f"{total} süresi dolmuş ziyaretçi hesabı ve talepleri silindi.")


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _run(args)
    except CommandError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    except OperationalError:
        print(
            "Hata: Veritabanına ulaşılamadı; adresi (TALEPAKIS_DATABASE_URL) kontrol et.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
