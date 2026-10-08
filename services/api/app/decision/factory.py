"""Gerçek sağlayıcıları ayarlardan kurar. Ücretli çağrılar varsayılan olarak KAPALIDIR: bayrak
açık ve anahtar tanımlı değilse gerçek sağlayıcı kurulamaz (kazara ücretli çağrıyı önler)."""

from app.config import Settings
from app.decision.jev import JevProvider
from app.decision.llm_anthropic import AnthropicProvider


class PaidCallsDisabled(RuntimeError):
    """Ücretli model çağrıları kapalı."""


class MissingApiKey(RuntimeError):
    """İstenen sağlayıcı için API anahtarı ortam değişkeninde yok."""


def jev_provider_from_settings(
    settings: Settings, *, timeout_s: float | None = None
) -> JevProvider:
    if not settings.paid_model_calls_enabled:
        raise PaidCallsDisabled(
            "Ücretli model çağrıları kapalı. Gerçek Jev çağrısı için bütçe onayından sonra "
            "TALEPAKIS_PAID_MODEL_CALLS_ENABLED=true verin."
        )
    if settings.jev_api_key is None:
        raise MissingApiKey(
            "TALEPAKIS_JEV_API_KEY tanımlı değil (anahtarı yalnızca ortam değişkeniyle verin)."
        )
    options = {} if timeout_s is None else {"timeout_s": timeout_s}
    return JevProvider(
        settings.jev_api_key.get_secret_value(),
        model=settings.jev_model,
        base_url=settings.jev_base_url,
        **options,
    )


def anthropic_provider_from_settings(settings: Settings) -> AnthropicProvider:
    if not settings.paid_model_calls_enabled:
        raise PaidCallsDisabled(
            "Ücretli model çağrıları kapalı. Gerçek LLM çağrısı için bütçe onayından sonra "
            "TALEPAKIS_PAID_MODEL_CALLS_ENABLED=true verin."
        )
    if settings.anthropic_api_key is None:
        raise MissingApiKey(
            "TALEPAKIS_ANTHROPIC_API_KEY tanımlı değil (anahtarı yalnızca ortam değişkeniyle "
            "verin)."
        )
    return AnthropicProvider(
        settings.anthropic_api_key.get_secret_value(),
        model=settings.anthropic_model,
        base_url=settings.anthropic_base_url,
    )
