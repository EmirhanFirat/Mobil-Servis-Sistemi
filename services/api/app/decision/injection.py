"""Talimat enjeksiyonu şüphesi: kullanıcı metni VERİDİR, talimat değildir.

Metin hiçbir zaman sağlayıcıya talimat olarak verilmez (yalnızca `state` verisi olarak taşınır).
Bu kontrol ek bir önlemdir: modeli yönlendirmeye çalışan bir ifade görülürse karar, hangi strateji
üretmiş olursa olsun insan incelemesine gider. Liste tam değildir; asıl koruma, metnin veri
olarak taşınması ve model çıktısına yetki verilmemesidir.
"""

import re

from app.decision.contract import DecisionInput
from app.decision.text import normalize

_PATTERNS = (
    r"(onceki|yukaridaki|tum|butun) (talimat|komut|kural|yonerge)",
    r"talimatlar\w* (yok say|unut|gormezden)",
    r"\byok say\b",
    r"ignore (all |the |any )?(previous|above|prior|earlier)",
    r"system prompt|sistem (mesaj|istem|talimat)",
    r"rol\w* unut",
    r"you are now|sen artik",
    r"kategori\w* .{0,25}(sec|olarak (ayarla|belirle|isaretle))",
    r"onceli\w* .{0,25}(yuksek|acil) (yap|sec|olarak)",  # öncelik / önceliği (k→ğ yumuşaması)
)
_COMPILED = tuple(re.compile(pattern) for pattern in _PATTERNS)


def looks_like_injection(data: DecisionInput) -> bool:
    text = normalize(f"{data.title} {data.description} {data.location}")
    return any(pattern.search(text) for pattern in _COMPILED)
