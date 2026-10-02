"""Dört stratejinin (rule_based, llm_only, jev_only, hybrid) ortak karar sözleşmesi.

İlkeler:
- Her soru tek bir yargıyı değerlendirir (kategori, öncelik, her eksik bilgi türü ayrı).
- Sağlayıcıya özgü olasılık/güven değerleri `Judgment` içinde, karar alanlarından AYRI saklanır.
- Bulunmayan güven değeri uydurulmaz (None). LLM'in kendi yazdığı yüzde ile Jev'in olasılıktan
  türetilen güveni farklı türdür (`ConfidenceKind`) ve birbirine eşdeğer sayılmaz.
- Sağlayıcı kullanım (token) bilgisi vermezse alan None'dır; tahmin ise `usage_estimated=True`.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.vocabulary import Category, MissingInfo, Priority


class StrategyName(StrEnum):
    RULE_BASED = "rule_based"
    LLM_ONLY = "llm_only"
    JEV_ONLY = "jev_only"
    HYBRID = "hybrid"


class Question(StrEnum):
    """Her biri tek bir yargı. Kategori ve öncelik kapalı seçenekli, eksik bilgiler evet/hayır."""

    CATEGORY = "category"
    PRIORITY = "priority"
    MISSING_LOCATION = "missing_location"
    MISSING_DETAIL = "missing_detail"
    MISSING_CONTACT = "missing_contact"
    MISSING_TIMING = "missing_timing"


MISSING_QUESTIONS: dict[Question, MissingInfo] = {
    Question.MISSING_LOCATION: MissingInfo.LOCATION,
    Question.MISSING_DETAIL: MissingInfo.DETAIL,
    Question.MISSING_CONTACT: MissingInfo.CONTACT,
    Question.MISSING_TIMING: MissingInfo.TIMING,
}

ALL_QUESTIONS: tuple[Question, ...] = tuple(Question)

# Eksik bilgi türlerinden hangisi otomatik ekip kuyruğunu ENGELLER (karar insan incelemesine gider).
# Yalnızca konum ve açıklama: bunlar olmadan görevli işe başlayamaz. İletişim ve başlangıç zamanı
# talebe etiket olarak yazılır (yönetici/görevli panelinde görünür), yönlendirmeyi değiştirmez.
BLOCKING_MISSING = frozenset({MissingInfo.LOCATION, MissingInfo.DETAIL})


class QuestionRole(StrEnum):
    """Bir sorunun ÜRÜN KARARINA etkisi. Hibritin ücretli LLM aşamasını yalnızca DECISION
    soruları tetikleyebilir: ürünün sonucunu değiştirmeyen sorudaki belirsizlik para harcatmaz."""

    # Cevap talebin kategorisini/önceliğini/ekibini belirler veya otomatik yönlendirmeyi engeller.
    DECISION = "decision"
    # Cevap yalnızca bilgi amaçlıdır (talebin `missing_info` etiketi); yönlendirme ve inceleme
    # kararını etkilemez.
    INFORMATIONAL = "informational"


def _role(question: Question) -> QuestionRole:
    if question in (Question.CATEGORY, Question.PRIORITY):
        return QuestionRole.DECISION
    if MISSING_QUESTIONS[question] in BLOCKING_MISSING:
        return QuestionRole.DECISION
    return QuestionRole.INFORMATIONAL


# Roller BLOCKING_MISSING'den TÜRETİLİR: iki yerde ayrı ayrı tutulup birbirinden sapamaz.
QUESTION_ROLES: dict[Question, QuestionRole] = {q: _role(q) for q in ALL_QUESTIONS}
DECISION_QUESTIONS: frozenset[Question] = frozenset(
    q for q, role in QUESTION_ROLES.items() if role is QuestionRole.DECISION
)
INFORMATIONAL_QUESTIONS: frozenset[Question] = frozenset(ALL_QUESTIONS) - DECISION_QUESTIONS

# Kapalı seçenekli sorularda her zaman bulunan "belirsiz / hiçbiri" seçeneği. Model zorla bir
# sınıfa itilmez; belirsizlik insan incelemesine gider.
UNCLEAR = "unclear"

CATEGORY_OPTIONS: tuple[str, ...] = (*(c.value for c in Category), UNCLEAR)
PRIORITY_OPTIONS: tuple[str, ...] = (*(p.value for p in Priority), UNCLEAR)


class ConfidenceKind(StrEnum):
    # Jev'in yanıtındaki `confidence`: (p_max − 1/n) / (1 − 1/n). Seçenek sayısı n'ye bağlıdır.
    JEV_CONFIDENCE = "jev_confidence"
    # Sağlayıcı olasılık verdi, güveni biz türettik (ör. evet/hayır için |2p − 1|).
    DERIVED_MARGIN = "derived_margin"
    # LLM'in kendi yazdığı yüzde. Kalibre değildir; Jev güveniyle karşılaştırılamaz.
    SELF_REPORTED = "self_reported"


class CallStatus(StrEnum):
    OK = "ok"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    SCHEMA_ERROR = "schema_error"
    UNAVAILABLE = "unavailable"
    AUTH_ERROR = "auth_error"
    BAD_REQUEST = "bad_request"


@dataclass(frozen=True)
class DecisionInput:
    """Sağlayıcıya giden asgari durum. Kullanıcı adı, kimlik ve geçmiş taşınmaz (gereksiz
    kişisel veri yok; ayrıca fazla bağlam doğruluğu düşürür). Metin her zaman VERİ olarak
    taşınır, talimat olarak değil."""

    title: str
    description: str
    location: str


@dataclass(frozen=True)
class Judgment:
    """Tek bir sorunun cevabı ve sağlayıcıya özgü sinyalleri.

    answer: kategori/öncelik için seçenek kodu; eksik bilgi için True/False; belirsizlikte None.
    """

    question: Question
    answer: str | bool | None
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    confidence_kind: ConfidenceKind | None = None
    n_options: int | None = None
    # Hangi sağlayıcıdan geldi; hibritte Jev'in yerine LLM yargısı benimsenince Jev'inki
    # `adopted=False` olarak kayıtta kalır (izlenebilirlik), karara girmez.
    source: str | None = None
    adopted: bool = True

    @property
    def abstained(self) -> bool:
        return self.answer is None or self.answer == UNCLEAR


def unresolved_questions(judgments: tuple[Judgment, ...] | list[Judgment]) -> tuple[Question, ...]:
    """Karara girmiş KESİN yanıtı olmayan sorular (soru sırasıyla). Benimsenmeyen ve çekimser
    yargılar sayılmaz. Bu sorular için "eksik değil" demek yanlıştır: bilinmiyorlar."""
    resolved = {j.question for j in judgments if j.adopted and not j.abstained}
    return tuple(q for q in ALL_QUESTIONS if q not in resolved)


def probability_floor(confidence: float, n_options: int) -> float:
    """Jev güven formülünün tersi: güveni `confidence` olan bir yanıtın en büyük olasılığı en az kaç
    olmalı? Jev `confidence = (p_max − 1/n) / (1 − 1/n)` verir (n: seçenek sayısı); aynı eşik
    farklı soru türlerinde farklı olasılık gerektirir (n=2: 0,80; n=4: 0,70; n=6: 0,67 için 0,6)."""
    if n_options < 2:
        raise ValueError("Seçenek sayısı en az 2 olmalı.")
    return 1 / n_options + confidence * (1 - 1 / n_options)


@dataclass(frozen=True)
class CallRecord:
    """Bir sağlayıcı çağrısı denemesi (başarılı veya başarısız). Her deneme ayrı kayıttır; böylece
    retry ve fallback maliyetleri toplama dahil olur."""

    strategy: StrategyName
    provider: str
    model: str  # gerçek model sürümü, takma ad değil
    prompt_version: str
    questions: tuple[Question, ...]
    status: CallStatus
    attempt: int = 1
    call_id: UUID = field(default_factory=uuid4)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int | None = None  # uygulama süresi (ağ dahil)
    provider_duration_ms: int | None = None  # sağlayıcı raporladıysa, ayrı tutulur
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_estimated: bool = False
    cost_usd: Decimal | None = None
    request_id: str | None = None
    error: str | None = None  # kısa; kullanıcı metni veya kişisel veri içermez
    is_mock: bool = False


@dataclass(frozen=True)
class Decision:
    decision_id: UUID
    strategy: StrategyName
    category: Category | None
    priority: Priority | None
    missing_info: tuple[MissingInfo, ...]
    review_required: bool
    review_reasons: tuple[str, ...]
    # Sağlayıcıya özgü sinyaller (olasılık, güven): karar alanlarından ayrı.
    judgments: tuple[Judgment, ...]
    calls: tuple[CallRecord, ...]
    providers: tuple[str, ...]
    model_versions: tuple[str, ...]
    is_mock: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_cost_usd(self) -> Decimal | None:
        """Tüm çağrıların (retry ve fallback dahil) toplamı; bilinmeyen çağrı varsa None."""
        return total_cost(self.calls)


def total_cost(calls: tuple[CallRecord, ...] | list[CallRecord]) -> Decimal | None:
    """Toplam ücret. Maliyeti bilinmeyen (kullanım bildirilmemiş) bir çağrı varsa None döner;
    bilinmeyen kısım sıfır sayılıp gizlenmez. Bilinen kısım için `known_cost`."""
    if unknown_cost_count(calls):
        return None
    return known_cost(calls)


def known_cost(calls: tuple[CallRecord, ...] | list[CallRecord]) -> Decimal:
    return sum((call.cost_usd for call in calls if call.cost_usd is not None), Decimal(0))


def unknown_cost_count(calls: tuple[CallRecord, ...] | list[CallRecord]) -> int:
    return sum(call.cost_usd is None for call in calls)


class BudgetExhausted(Exception):
    """Bir çağrı, harcama sınırını aşabileceği için GÖNDERİLMEDİ (veya üst sınırı hesaplanamadığı
    için gönderilemez). Sağlayıcı hatası DEĞİLDİR: yeniden denenmez, başka sağlayıcıya geçilmez,
    tüm çalıştırmayı durdurur. `calls`, bu karar için o ana dek yapılmış çağrıların kayıtlarıdır
    (harcanan ücret kaybolmasın)."""

    def __init__(self, message: str, calls: tuple[CallRecord, ...] = ()):
        super().__init__(message)
        self.calls = calls


class DecisionUnavailable(Exception):
    """Sağlayıcı sınırlı retry'dan sonra da yanıt veremedi. Talep etkilenmez (kaybolmaz); çağıran
    görünür bir hata durumu yazar. Başarısız denemelerin kayıtları maliyet için taşınır."""

    def __init__(self, message: str, calls: tuple[CallRecord, ...] = ()):
        super().__init__(message)
        self.calls = calls
