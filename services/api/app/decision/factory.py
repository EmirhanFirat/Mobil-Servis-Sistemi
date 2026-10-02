"""Gerçek sağlayıcıları ayarlardan kurar. Ücretli çağrılar varsayılan olarak KAPALIDIR: bayrak
açık ve anahtar tanımlı değilse gerçek sağlayıcı kurulamaz (kazara ücretli çağrıyı önler)."""

from app.config import Settings
from app.decision.jev import JevProvider


class PaidCallsDisabled(RuntimeError):
    """Ücretli model çağrıları kapalı."""


class MissingApiKey(RuntimeError):
    """İstenen sağlayıcı için API anahtarı ortam değişkeninde yok."""


def jev_provider_from_settings(settings: Settings) -> JevProvider:
    if not settings.paid_model_calls_enabled:
        raise PaidCallsDisabled(
            "Ücretli model çağrıları kapalı. Gerçek Jev çağrısı için bütçe onayından sonra "
            "TALEPAKIS_PAID_MODEL_CALLS_ENABLED=true verin."
        )
    if settings.jev_api_key is None:
        raise MissingApiKey(
            "TALEPAKIS_JEV_API_KEY tanımlı değil (anahtarı yalnızca ortam değişkeniyle verin)."
        )
    return JevProvider(
        settings.jev_api_key.get_secret_value(),
        model=settings.jev_model,
        base_url=settings.jev_base_url,
    )
