from fastapi import APIRouter, Request

from app.deps import CurrentUser, DbSession, SettingsDep
from app.errors import AppError, too_many_attempts
from app.hardening import LoginThrottleDep, client_ip
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.security import create_access_token
from app.services import accounts

router = APIRouter(prefix="/auth", tags=["giriş"])


@router.post("/login", response_model=TokenResponse, summary="Kullanıcı adı ve parolayla giriş")
def login(
    data: LoginRequest,
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    throttle: LoginThrottleDep,
) -> TokenResponse:
    ip = client_ip(request, settings)
    # Engelliyken parola hiç doğrulanmaz (doğru parola bile reddedilir) ve hesabın var olup
    # olmadığı yanıttan anlaşılmaz.
    wait = throttle.retry_after(ip, data.username)
    if wait:
        raise too_many_attempts(wait)
    try:
        user = accounts.authenticate(db, data.username, data.password)
    except AppError as exc:
        if exc.status_code == 401:
            throttle.record_failure(ip, data.username)
        raise
    throttle.record_success(ip, data.username)
    return TokenResponse(
        access_token=create_access_token(user.id, settings, password_hash=user.password_hash),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut, summary="Oturumdaki kullanıcı")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
