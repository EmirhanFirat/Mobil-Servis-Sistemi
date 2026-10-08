"""Parola özeti ve oturum belirteci. Kriptografi güvenilir kütüphanelerde (argon2-cffi, PyJWT)."""

import hashlib
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


def password_version(password_hash: str) -> str:
    """Parola özetinden türetilen kısa parmak izi. Belirtece konur; parola değişince (özet
    değişir) eski belirteçler geçersiz olur. Özetin kendisi belirteçte taşınmaz (geri
    alınamaz, kısaltılmış)."""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def create_access_token(
    user_id: UUID, settings: Settings, *, password_hash: str, minutes: int | None = None
) -> str:
    """`minutes` verilmezse `access_token_minutes` (demo ziyaretçileri daha kısa ömürlüdür)."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "pv": password_version(password_hash),
        "iat": now,
        "exp": now + timedelta(minutes=minutes or settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> tuple[UUID, str] | None:
    """Geçerli belirteçteki (kullanıcı kimliği, parola sürümü); geçersiz, süresi dolmuş veya
    parola sürümü olmayan belirteçte None."""
    try:
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub", "pv"]},
        )
        version = claims["pv"]
        if not isinstance(version, str):
            return None
        return UUID(claims["sub"]), version
    except (jwt.PyJWTError, ValueError):
        return None
