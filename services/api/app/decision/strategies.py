"""Sağlayıcı tabanlı stratejiler: llm_only, jev_only ve hybrid.

Aynı karar görevi, aynı sorular, aynı asgari durum: stratejiler yalnızca KİMİN yanıtladığıyla
ayrışır (adil karşılaştırma). rule_based için bkz. rule_based.py.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from app.decision.assemble import assemble
from app.decision.contract import (
    ALL_QUESTIONS,
    BudgetExhausted,
    CallRecord,
    Decision,
    DecisionInput,
    DecisionUnavailable,
    Judgment,
    Question,
    StrategyName,
)
from app.decision.providers import Provider
from app.decision.retry import DEFAULT_RETRY, RetryPolicy, classify_with_retry


class ProviderStrategy:
    """Tek sağlayıcı, tüm sorular tek çağrıda (llm_only ve jev_only)."""

    def __init__(
        self,
        name: StrategyName,
        provider: Provider,
        retry: RetryPolicy = DEFAULT_RETRY,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.name = name
        self.provider = provider
        self.retry = retry
        self.sleep = sleep

    def decide(self, data: DecisionInput) -> Decision:
        result, calls = classify_with_retry(
            self.provider, data, ALL_QUESTIONS, self.name, self.retry, self.sleep
        )
        return assemble(
            strategy=self.name,
            data=data,
            judgments=list(result.judgments),
            calls=calls,
            providers=(self.provider.name,),
            model_versions=(self.provider.model,),
        )


@dataclass(frozen=True)
class HybridThresholds:
    """Jev'in "yeterli güven" eşiği, soru başına. Doğrulama kümesinde ayarlanır (test kümesinde
    değil). Varsayılanlar bilinçli olarak muhafazakârdır; ölçümle değişecektir."""

    jev_min_confidence: dict[Question, float] = field(
        default_factory=lambda: dict.fromkeys(ALL_QUESTIONS, 0.6)
    )
    # LLM'in kendi yazdığı güven Jev güveniyle karşılaştırılmaz; yalnızca isteğe bağlı bir
    # çekimserlik kapısıdır (None = kullanma; LLM'in "belirsiz" demesi zaten çekimserliktir).
    llm_min_self_reported: float | None = None


class HybridStrategy:
    """Jev yeterince güvenemediği sorularda LLM'e, çözülemeyenlerde insana aktarır.

    Sessiz sağlayıcı değişimi YOK: Jev çağrısı kalıcı olarak başarısız olursa LLM'e geçilmez,
    DecisionUnavailable fırlar (görünür hata). LLM yalnızca Jev'in YANITLADIĞI ama güvenmediği
    sorular için çağrılır. LLM ikinci aşaması başarısız olursa o sorular çözülmemiş kalır ve
    karar insan incelemesine gider (Jev'in güvenli yanıtları korunur).
    """

    name = StrategyName.HYBRID

    def __init__(
        self,
        jev: Provider,
        llm: Provider,
        thresholds: HybridThresholds | None = None,
        retry: RetryPolicy = DEFAULT_RETRY,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.jev = jev
        self.llm = llm
        self.thresholds = thresholds or HybridThresholds()
        self.retry = retry
        self.sleep = sleep

    def _confident(self, judgment: Judgment) -> bool:
        if judgment.abstained or judgment.confidence is None:
            return False
        return judgment.confidence >= self.thresholds.jev_min_confidence[judgment.question]

    def _llm_accepts(self, judgment: Judgment) -> bool:
        if judgment.abstained:
            return False
        floor = self.thresholds.llm_min_self_reported
        return floor is None or (judgment.confidence is not None and judgment.confidence >= floor)

    def decide(self, data: DecisionInput) -> Decision:
        # 1) Jev, tüm sorular. Başarısızsa DecisionUnavailable yukarı çıkar (sessiz geçiş yok).
        jev_result, calls = classify_with_retry(
            self.jev, data, ALL_QUESTIONS, self.name, self.retry, self.sleep
        )
        judgments: list[Judgment] = []
        uncertain: list[Question] = []
        for judgment in jev_result.judgments:
            if self._confident(judgment):
                judgments.append(judgment)
            else:
                uncertain.append(judgment.question)
                judgments.append(replace(judgment, adopted=False))  # kayıtta kalır, karara girmez

        providers = [self.jev.name]
        models = [self.jev.model]
        reasons: list[str] = []

        # 2) Yalnızca güvenilmeyen sorular LLM'e.
        if uncertain:
            providers.append(self.llm.name)
            models.append(self.llm.model)
            try:
                llm_result, llm_calls = classify_with_retry(
                    self.llm, data, tuple(uncertain), self.name, self.retry, self.sleep
                )
            except BudgetExhausted as stop:
                # Harcama sınırı bir hata değil durma sinyalidir: yutulmaz, Jev aşamasının
                # (ücretlendirilmiş) çağrı kayıtlarıyla birlikte yukarı çıkar.
                stop.calls = (*calls, *stop.calls)
                raise
            except DecisionUnavailable as failure:
                calls.extend(failure.calls)
                reasons.append("llm_unavailable")
                judgments.extend(Judgment(q, None, source=self.llm.name) for q in uncertain)
            else:
                calls.extend(llm_calls)
                for judgment in llm_result.judgments:
                    if self._llm_accepts(judgment):
                        judgments.append(judgment)
                    else:
                        # LLM de karar veremedi: çözülemeyen soru → insan incelemesi.
                        judgments.append(replace(judgment, answer=None))

        return assemble(
            strategy=self.name,
            data=data,
            judgments=judgments,
            calls=_ordered(calls),
            providers=tuple(providers),
            model_versions=tuple(models),
            extra_reasons=tuple(reasons),
        )


def _ordered(calls: list[CallRecord]) -> list[CallRecord]:
    return sorted(calls, key=lambda call: call.started_at)
