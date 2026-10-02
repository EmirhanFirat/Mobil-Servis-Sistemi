"""Sağlayıcı arayüzü ve hata türleri. Jev, ekonomik LLM ve mock adaptörleri bunu uygular;
ürün kodu sağlayıcıya değil bu arayüze bağlıdır (sağlayıcı değiştirmek ürünü yeniden yazdırmaz)."""

from dataclasses import dataclass
from typing import Protocol

from app.decision.contract import (
    CallRecord,
    CallStatus,
    DecisionInput,
    Judgment,
    Question,
    StrategyName,
)
from app.decision.pricing import PriceEntry

RETRYABLE = frozenset(
    {CallStatus.TIMEOUT, CallStatus.RATE_LIMITED, CallStatus.SCHEMA_ERROR, CallStatus.UNAVAILABLE}
)


class ProviderError(Exception):
    """Bir deneme başarısız oldu. `record`, başarısız denemenin kaydıdır (süre, durum, varsa
    kullanım); böylece retry'ın maliyeti ve süresi de toplama girer."""

    def __init__(
        self,
        status: CallStatus,
        message: str,
        record: CallRecord,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.record = record
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE


@dataclass(frozen=True)
class ProviderResult:
    judgments: tuple[Judgment, ...]
    call: CallRecord


class Provider(Protocol):
    name: str  # "jev" | "anthropic" | "mock-jev" ...
    model: str  # gerçek model sürümü
    prompt_version: str
    price: PriceEntry | None

    def classify(
        self, data: DecisionInput, questions: tuple[Question, ...], strategy: StrategyName
    ) -> ProviderResult:
        """Verilen soruları tek çağrıda yanıtlar. Başarısızlıkta ProviderError fırlatır."""
        ...
