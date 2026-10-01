from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """İstemciye gösterilebilir iş kuralı hatası.

    Yanıt gövdesi: {"detail": <Türkçe mesaj>, "code": <kod>}.
    """

    def __init__(
        self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def not_found(message: str = "Kayıt bulunamadı.") -> AppError:
    return AppError(404, "not_found", message)


def forbidden(message: str = "Bu işlem için yetkin yok.") -> AppError:
    return AppError(403, "forbidden", message)


def conflict(code: str, message: str) -> AppError:
    return AppError(409, code, message)


def unauthorized(message: str = "Oturum açman gerekiyor.") -> AppError:
    return AppError(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code},
            headers=exc.headers,
        )
