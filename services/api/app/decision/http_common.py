"""Ham HTTP sağlayıcı adaptörlerinin (Jev, Anthropic) ortak yardımcıları: yanıt doğrulama,
Retry-After ve kullanım okuma, HTTP durum kodunun çağrı durumuna eşlenmesi."""

from typing import Any

import httpx

from app.decision.contract import CallStatus


class SchemaError(ValueError):
    """Yanıt belgelenmiş şemaya uymuyor."""


def number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SchemaError(f"{name} sayı değil")
    return float(value)


def unit(value: Any, name: str) -> float:
    result = number(value, name)
    if not 0.0 <= result <= 1.0:
        raise SchemaError(f"{name} 0–1 aralığında değil")
    return result


def reported_tokens(usage: Any, field: str) -> int | None:
    """Sağlayıcının bildirdiği token sayısı; bildirilmediyse veya geçersizse None (uydurulmaz)."""
    value = usage.get(field) if isinstance(usage, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def retry_after_seconds(response: httpx.Response) -> float | None:
    """`retry-after-ms` veya `retry-after` (saniye) başlığı; ayrıştırılamazsa None."""
    for header, scale in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        raw = response.headers.get(header)
        if raw is None:
            continue
        try:
            value = float(raw) / scale
        except ValueError:
            continue
        if value >= 0:
            return value
    return None


def status_for_http(code: int) -> CallStatus:
    # 402 (faturalandırma) da hesap/kimlik sorunudur: yeniden denemek işe yaramaz.
    if code in (401, 402, 403):
        return CallStatus.AUTH_ERROR
    if code in (408, 504):
        return CallStatus.TIMEOUT
    if code == 429:
        return CallStatus.RATE_LIMITED
    if code >= 500:  # 529 (aşırı yük) dahil
        return CallStatus.UNAVAILABLE
    return CallStatus.BAD_REQUEST  # 400/413/422/diğer 4xx: bizim isteğimizde hata, yeniden denenmez
