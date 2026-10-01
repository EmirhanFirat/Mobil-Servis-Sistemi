from fastapi import APIRouter

from app.deps import CurrentUser, DbSession, SettingsDep
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.security import create_access_token
from app.services import accounts

router = APIRouter(prefix="/auth", tags=["giriş"])


@router.post("/login", response_model=TokenResponse, summary="Kullanıcı adı ve parolayla giriş")
def login(data: LoginRequest, db: DbSession, settings: SettingsDep) -> TokenResponse:
    user = accounts.authenticate(db, data.username, data.password)
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut, summary="Oturumdaki kullanıcı")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
