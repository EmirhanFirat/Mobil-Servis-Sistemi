"""rule_based: açık anahtar kelime ve iş kurallarıyla basit karşılaştırma tabanı.

Bilinçli olarak basittir. Bilinen zayıflıkları (benchmark'ta ölçülür, düzeltilmez):
yazım hatası, çok sorunlu mesaj, dolaylı anlatım ve talimat enjeksiyonu ("elektrik seç" yazan
metindeki "elektrik" kelimesini sayar). Model çağrısı yapmaz; maliyeti sıfırdır.

Köklerin yazımı: "priz" = önek eşleşmesi ("prizden"), "=su" = yalnızca tam kelime,
"sicak su" = boşluklu ifade (alt dize).
"""

from app.decision.assemble import assemble
from app.decision.contract import (
    UNCLEAR,
    Decision,
    DecisionInput,
    Judgment,
    Question,
    StrategyName,
)
from app.decision.safety import HAZARD_TERMS
from app.decision.text import normalize, words
from app.domain.vocabulary import Category, Priority

RULES_VERSION = "kurallar-1"

# Ağırlık: güçlü ipucu 2, zayıf ipucu 1.
STRONG: dict[Category, tuple[str, ...]] = {
    Category.ELECTRICAL: (
        "priz",
        "elektrik",
        "sigorta",
        "kablo",
        "kivilcim",
        "aydinlatma",
        "ampul",
        "floresan",
        "voltaj",
        "kisa devre",
        "uzatma",
        "trafo",
    ),
    Category.PLUMBING: (
        "lavabo",
        "musluk",
        "tesisat",
        "klozet",
        "tikan",
        "tikal",
        "sizinti",
        "akit",
        "akiyor",
        "sicak su",
        "=gider",
        "rezervuar",
        "sifon",
        "=dus",
        "dusta",
        "batarya",
    ),
    Category.IT_NETWORK: (
        "internet",
        "wifi",
        "wi-fi",
        "modem",
        "yazici",
        "bilgisayar",
        "kablosuz",
        "ethernet",
        "eduroam",
        "baglanti",
        "ag erisim",
    ),
    Category.CLEANING: (
        "temizlik",
        "cop",
        "kirli",
        "supurge",
        "paspas",
        "pislik",
        "kirlen",
        "hijyen",
    ),
    Category.OTHER: (
        "asansor",
        "kapi",
        "pencere",
        "dolap",
        "mobilya",
        "yatak",
        "kalorifer",
        "klima",
        "boya",
        "bocek",
        "kilit",
        "mentese",
        "cati",
    ),
}
WEAK: dict[Category, tuple[str, ...]] = {
    Category.ELECTRICAL: ("isik", "yanmiyor", "lamba", "elektr"),
    Category.PLUMBING: ("=su", "damla", "koku", "tuvalet"),
    Category.IT_NETWORK: ("sifre", "=ag", "hesap"),
    Category.CLEANING: ("toz", "koku", "tuvalet"),
    Category.OTHER: ("ariza", "bozuk", "kirik"),
}

HIGH_TERMS = ("acil", "hemen", "derhal", "yayiliyor", "tasiyor", "sizintisi var")
LOW_TERMS = ("onemli degil", "acelesi yok", "acele degil", "kucuk bir", "zamani gelince")

GENERIC_LOCATIONS = frozenset({"burasi", "burada", "yok", "bilmiyorum", "?", "-", "orasi", "orada"})


def _hits(normalized: str, tokens: list[str], stems: tuple[str, ...]) -> int:
    """Eşleşen farklı kök sayısı."""
    count = 0
    for stem in stems:
        if stem.startswith("="):
            hit = stem[1:] in tokens
        elif " " in stem:
            hit = stem in normalized
        else:
            hit = any(token.startswith(stem) for token in tokens)
        count += hit
    return count


def score_categories(text: str) -> dict[Category, int]:
    """Metindeki ipuçlarına göre kategori puanları (güçlü=2, zayıf=1)."""
    normalized = normalize(text)
    tokens = words(normalized)
    return {
        category: 2 * _hits(normalized, tokens, STRONG[category])
        + _hits(normalized, tokens, WEAK[category])
        for category in Category
    }


def pick_category(scores: dict[Category, int]) -> tuple[Category | None, bool]:
    """(kategori, çok_sorun_mu). Beraberlikte veya hiç ipucu yoksa belirsiz (None)."""
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    (top, top_score), (_, second_score) = ranked[0], ranked[1]
    if top_score == 0 or top_score == second_score:
        return None, False
    strong_categories = [category for category, score in scores.items() if score >= 2]
    return top, len(strong_categories) >= 2


def pick_priority(text: str) -> Priority:
    normalized = normalize(text)
    if any(term in normalized for term in LOW_TERMS):
        return Priority.LOW
    if any(term in normalized for term in HIGH_TERMS):
        return Priority.HIGH
    if any(term in normalized for term in HAZARD_TERMS):
        return Priority.HIGH
    return Priority.NORMAL


def missing_flags(data: DecisionInput) -> dict[Question, bool | None]:
    """Yalnızca açıkça tespit edilebilenler; diğerleri None (değerlendirilmedi)."""
    location = normalize(data.location)
    description_words = words(normalize(data.description))
    return {
        Question.MISSING_LOCATION: len(location) < 4 or location in GENERIC_LOCATIONS,
        Question.MISSING_DETAIL: len(description_words) < 4,
        Question.MISSING_CONTACT: None,
        Question.MISSING_TIMING: None,
    }


class RuleBasedStrategy:
    name = StrategyName.RULE_BASED

    def decide(self, data: DecisionInput) -> Decision:
        text = f"{data.title} {data.description}"
        category, multiple = pick_category(score_categories(text))
        priority = pick_priority(text)

        judgments = [
            Judgment(Question.CATEGORY, category.value if category else UNCLEAR),
            Judgment(Question.PRIORITY, priority.value),
            *(Judgment(question, answer) for question, answer in missing_flags(data).items()),
        ]
        return assemble(
            strategy=self.name,
            data=data,
            judgments=judgments,
            calls=[],
            providers=("rule_based",),
            model_versions=(RULES_VERSION,),
            extra_reasons=("multiple_issues",) if multiple else (),
        )
