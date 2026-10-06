"""Sunucuda çalıştırılan yönetim komutları (HTTP ucu değildir; yalnızca veritabanına erişimi olan
operatör kullanır).

Üretimde demo verisi yüklenmez (`app.seed` reddeder), bu yüzden ilk yönetici buradan oluşturulur:

  python -m app.manage create-admin --username yonetici --display-name "Ad Soyad"
  python -m app.manage reset-password --username yonetici

Parola komut satırı argümanı OLARAK VERİLMEZ (kabuk geçmişine ve süreç listesine girer):
etkileşimli olarak iki kez sorulur ya da `--password-stdin` ile standart girdiden bir satır
okunur. Parola hiçbir yere yazdırılmaz. Parola değişince o hesabın mevcut oturum belirteçleri
geçersiz olur.
"""

import argparse
import getpass
import sys
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import get_engine
from app.domain.vocabulary import Role
from app.errors import AppError
from app.models import User
from app.schemas import UserCreate
from app.security import hash_password
from app.services import accounts

# Yönetici parolası için, genel kullanıcı kuralından (8) daha sıkı alt sınır.
MIN_ADMIN_PASSWORD_LENGTH = 12


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


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Parola: ")
    if first != getpass.getpass("Parola (tekrar): "):
        raise CommandError("İki parola aynı değil.")
    return first


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        password = _read_password(args.password_stdin)
        with Session(get_engine()) as db:
            if args.command == "create-admin":
                user = create_admin(db, args.username, args.display_name, password)
                print(f"Yönetici oluşturuldu: {user.username}")
            else:
                user = reset_password(db, args.username, password)
                print(f"Parola değiştirildi: {user.username} (eski oturumları geçersiz oldu).")
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
