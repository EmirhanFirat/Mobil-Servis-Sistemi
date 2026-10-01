from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.db import get_db
from app.domain.vocabulary import Role
from app.errors import forbidden, unauthorized
from app.models import User
from app.security import decode_access_token

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_bearer = HTTPBearer(auto_error=False, description="Giriş yanıtındaki access_token")


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
    settings: SettingsDep,
) -> User:
    if credentials is None:
        raise unauthorized()
    user_id = decode_access_token(credentials.credentials, settings)
    if user_id is None:
        raise unauthorized("Oturumun geçersiz veya süresi dolmuş. Yeniden giriş yap.")
    # Rol ve aktiflik her istekte veritabanından okunur; belirteçteki bilgiye güvenilmez.
    user = db.scalar(
        select(User).options(selectinload(User.teams)).where(User.id == user_id, User.is_active)
    )
    if user is None:
        raise unauthorized("Hesap bulunamadı veya devre dışı.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not Role.ADMIN:
        raise forbidden("Bu işlem yalnızca yöneticiler içindir.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
