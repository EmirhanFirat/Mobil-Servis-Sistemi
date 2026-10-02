"""Sınırlı retry: sonsuz tekrar yok, sessizce başka sağlayıcıya geçiş yok.

Her deneme ayrı bir CallRecord olarak döner (başarısızlar dahil), böylece retry maliyeti ve süresi
toplamlara girer. Kalıcı hata veya deneme hakkı bitince DecisionUnavailable fırlatılır; çağıran
bunu görünür bir hata durumuna çevirir ve talep kaybolmaz.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from app.decision.contract import (
    BudgetExhausted,
    CallRecord,
    DecisionInput,
    DecisionUnavailable,
    Question,
    StrategyName,
)
from app.decision.pricing import compute_cost
from app.decision.providers import Provider, ProviderError, ProviderResult


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_s: float = 0.5
    factor: float = 2.0
    max_delay_s: float = 5.0

    def delay(self, attempt: int, retry_after: float | None) -> float:
        """Üstel bekleme; sağlayıcı Retry-After verdiyse onu (üst sınırla) esas alır."""
        backoff = min(self.base_delay_s * self.factor ** (attempt - 1), self.max_delay_s)
        if retry_after is not None:
            return min(max(retry_after, 0.0), self.max_delay_s)
        return backoff


DEFAULT_RETRY = RetryPolicy()


def _finalize(provider: Provider, record: CallRecord, attempt: int) -> CallRecord:
    # Fiyat yalnızca yanıtı veren GERÇEK model sürümüyle eşleşiyorsa uygulanır. Sağlayıcı farklı
    # bir sürümle yanıtladıysa o sürümün fiyatı doğrulanmadığı için maliyet bilinmez (None).
    price = provider.price
    if price is not None and record.model != price.model:
        price = None
    cost = compute_cost(price, record.input_tokens, record.output_tokens)
    return replace(record, attempt=attempt, cost_usd=cost)


def classify_with_retry(
    provider: Provider,
    data: DecisionInput,
    questions: tuple[Question, ...],
    strategy: StrategyName,
    policy: RetryPolicy = DEFAULT_RETRY,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[ProviderResult, list[CallRecord]]:
    """(başarılı sonuç, tüm deneme kayıtları). Başarısız olursa DecisionUnavailable(calls=...)."""
    records: list[CallRecord] = []
    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = provider.classify(data, questions, strategy)
        except ProviderError as error:
            records.append(_finalize(provider, error.record, attempt))
            if not error.retryable or attempt == policy.max_attempts:
                reason = "yeniden denenemez" if not error.retryable else "deneme hakkı bitti"
                raise DecisionUnavailable(
                    f"{provider.name} yanıt vermedi ({error.status.value}; {reason}).",
                    calls=tuple(records),
                ) from error
            sleep(policy.delay(attempt, error.retry_after))
            continue
        except BudgetExhausted as stop:
            # Harcama sınırı: bu retry döngüsünde o ana dek harcananlar kayıpta kalmasın.
            stop.calls = (*records, *stop.calls)
            raise
        record = _finalize(provider, result.call, attempt)
        records.append(record)
        return ProviderResult(result.judgments, record), records
    raise AssertionError("ulaşılamaz")  # pragma: no cover
