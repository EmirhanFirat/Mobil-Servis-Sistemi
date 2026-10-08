"""Canlı demo uçlarının istek/yanıt şemaları. Ziyaretçiye yalnızca KENDİ talebinin sonucu döner;
yanıtta başka kullanıcının verisi, kullanıcı adı, bütçe tutarı veya sağlayıcı anahtarı bulunmaz."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, StringConstraints, field_validator

TITLE_MAX = 120
DESCRIPTION_MAX = 1000
LOCATION_MAX = 120

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=TITLE_MAX)]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=10, max_length=DESCRIPTION_MAX)
]
Location = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=LOCATION_MAX)
]


class DemoDecisionRequest(BaseModel):
    title: Title
    description: Description
    location: Location

    @field_validator("title", "description", "location")
    @classmethod
    def _no_nul(cls, value: str) -> str:
        # PostgreSQL metin sütunları NUL (\x00) kabul etmez; 500 yerine açık 422 verilsin.
        if "\x00" in value:
            raise ValueError("metin geçersiz karakter içeriyor")
        return value


# Hazırlık isteği (uyandırma): model çağrısı YAPMAZ.
DemoUnavailableReason = Literal["disabled", "not_configured", "budget_exhausted"]


class DemoLimits(BaseModel):
    title_max: int
    description_max: int
    location_max: int
    decisions_per_session: int
    session_minutes: int


class DemoStatus(BaseModel):
    api_ready: bool = True
    database_ready: bool
    database_ms: int | None  # Neon'un uyanma/sorgu süresi (yalnızca hazırlık isteğinde ölçülür)
    enabled: bool
    reason: DemoUnavailableReason | None
    provider: str | None  # "jev" | "mock"
    model: str | None
    is_mock: bool
    limits: DemoLimits
    retention_hours: int


class DemoSessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_s: int
    decisions_total: int
    limits: DemoLimits


DemoState = Literal[
    "pending",  # kaydedildi, henüz çalıştırılmadı (ör. sistem meşguldü)
    "running",  # başka bir istekte çalışıyor
    "completed",  # Jev kararı üretildi
    "skipped",  # model HİÇ çağrılmadı: talep karardan önce insan tarafından değiştirildi
    "failed",  # sağlayıcı yanıt vermedi/geçersiz yanıt (istek gönderildi, sonuç yok)
    "uncertain",  # istek gönderilmiş OLABİLİR, sonucu bilinmiyor; otomatik yeniden gönderilmedi
    "budget_exhausted",  # demo bütçesi doldu; istek gönderilmedi
]


class DemoJudgment(BaseModel):
    question: str
    answer: str | bool | None
    confidence: float | None
    # jev_confidence (Jev'in verdiği) | derived_margin (bizim türettiğimiz): aynı şey değil
    confidence_kind: str | None
    adopted: bool


class DemoDecisionInfo(BaseModel):
    category: str | None
    priority: str | None
    missing_info: list[str]
    review_required: bool
    review_explanations: list[str]
    applied: bool  # karar talebe uygulandı mı
    applied_outcome: str
    is_mock: bool
    provider: str | None
    model: str | None
    judgments: list[DemoJudgment]


class DemoUsage(BaseModel):
    calls: int
    # Sağlayıcının bildirdiği kullanım; bildirilmediyse None (uydurulmaz).
    input_tokens: int | None
    output_tokens: int | None
    output_tokens_free: bool  # Jev çıktı token'ları ücretsizdir (yine de sayılır)
    # USD, metin (Decimal). Bilinmiyorsa None ve cost_basis "unknown": sıfır DEĞİL.
    cost_usd: str | None
    cost_basis: Literal["provider_usage", "unknown"]
    price_note: str


class DemoTimings(BaseModel):
    jev_call_ms: int | None  # Jev çağrısı (ağ dahil), bizim ölçümümüz
    job_ms: int | None  # işin açılışından bitişine
    server_total_ms: int | None  # yalnızca bu isteğin sunucu süresi (POST yanıtında)


class DemoDecisionResult(BaseModel):
    ticket_id: UUID
    ticket_number: int
    state: DemoState
    message: str
    title: str
    description: str
    location: str
    ticket_status: str
    created_at: datetime
    decision: DemoDecisionInfo | None
    usage: DemoUsage | None
    timings: DemoTimings
    retry_after_s: int | None = None
    decisions_remaining: int


class DemoDecisionSummary(BaseModel):
    ticket_id: UUID
    ticket_number: int
    title: str
    state: DemoState
    created_at: datetime
