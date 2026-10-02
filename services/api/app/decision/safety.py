"""Güvenlik kapısı: can güvenliği ihtimali olan taleplerin otomatik yönlendirilmesini engeller.

Bu uygulama bir acil yardım sistemi değildir ve can güvenliği kararını otonom modele bırakmaz.
Metinde tehlike belirten bir ifade varsa karar, hangi strateji üretmiş olursa olsun:
  - önceliği en az "yüksek" yapar,
  - insan incelemesi ister (talep ekip kuyruğuna otomatik düşmez),
  - nedenini `review_reasons` içine yazar.

Liste bilinçli olarak geniştir (yanlış alarm, kaçırmaktan iyidir) ama GARANTİ DEĞİLDİR: yazım
hatası veya dolaylı anlatım kaçabilir. Arayüzde her zaman "112'yi ara" uyarısı vardır.
"""

from dataclasses import dataclass

from app.decision.contract import DecisionInput
from app.decision.text import normalize

# Normalleştirilmiş (küçük harf, aksansız) ifadeler. Alt dizi olarak aranır.
HAZARD_TERMS: tuple[str, ...] = (
    "yangin",
    "alev",
    "duman",
    "kivilcim",
    "yanik koku",
    "kisa devre",
    "elektrik carp",
    "carpildi",
    "carpiliyor",
    "gaz kacag",
    "gaz koku",
    "gaz sizinti",
    "patlama",
    "patladi",
    "su bast",
    "su baskin",
    "su basmasi",
    "tavan coktu",
    "cokme",
    "mahsur",
    "bayildi",
    "yaralan",
    "kanama",
    "intihar",
)


@dataclass(frozen=True)
class SafetyResult:
    flagged: bool
    terms: tuple[str, ...]


def check_safety(data: DecisionInput) -> SafetyResult:
    haystack = normalize(f"{data.title} {data.description}")
    found = tuple(term for term in HAZARD_TERMS if term in haystack)
    return SafetyResult(flagged=bool(found), terms=found)
