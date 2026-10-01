"""Parola özeti ve oturum belirteci. Kriptografi güvenilir kütüphanelerde (argon2-cffi, PyJWT)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import Settings

JWT_ALGORITHM = "HS256"

# Testler maliyeti düşük bir örnekle değiştirebilsin diye modül düzeyinde tutulur.
_hasher = PasswordHasher()
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        # VerifyMismatchError, VerificationError'ın alt sınıfıdır.
        return False


def burn_password_check(password: str) -> None:
    """Var olmayan kullanıcıda da aynı işi yap; yanıt süresi kullanıcı adını ele vermesin."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _hasher.hash("zamanlama-icin-sahte-parola")
    verify_password(_dummy_hash, password)


def create_access_token(user_id: UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> UUID | None:
    """Geçerli belirteçteki kullanıcı kimliğini döndürür; geçersiz veya süresi dolmuşsa None."""
    try:
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
