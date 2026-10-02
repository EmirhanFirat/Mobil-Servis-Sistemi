"""Deterministik mock sağlayıcılar. API anahtarı olmadan ürün geliştirmeye ve testlere izin verir.

UYARI: Mock çıktıları GERÇEK MODEL ÖLÇÜMÜ DEĞİLDİR. Kayıtlarda `is_mock=True` olarak işaretlenir,
arayüzde ve raporlarda mock olarak belirtilir; token sayıları tahmindir (`usage_estimated=True`).

İki davranış biçimi vardır:
- "jev": olasılık dağılımı döner; güven = (p_max − 1/n)/(1 − 1/n) (Jev belgesindeki formül).
  Evet/hayır sorularında güven, olasılıktan türetilen |2p − 1| kenar payıdır.
- "llm": olasılık DÖNMEZ (LLM'ler vermez); yalnızca kendi yazdığı güven yüzdesi vardır ve bu,
  Jev güveniyle karşılaştırılamaz (`ConfidenceKind.SELF_REPORTED`).

`script` ile hata enjekte edilebilir: her çağrı için bir adım; None = normal yanıt, CallStatus =
o hatayla başarısız ol.
"""

import math
import time
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from app.decision.contract import (
    CATEGORY_OPTIONS,
    PRIORITY_OPTIONS,
    UNCLEAR,
    CallRecord,
    CallStatus,
    ConfidenceKind,
    DecisionInput,
    Judgment,
    Question,
    StrategyName,
)
from app.decision.pricing import MOCK_JEV, MOCK_LLM, PriceEntry
from app.decision.providers import ProviderError, ProviderResult
from app.decision.rule_based import missing_flags, pick_priority, score_categories
from app.decision.safety import check_safety
from app.decision.text import normalize, words
from app.domain.vocabulary import Priority

Flavor = Literal["jev", "llm"]

TIME_WORDS = ("dun", "bugun", "gundur", "sabah", "aksam", "saat", "hafta", "beri", "once", "gece")
PHONE_OR_ROOM = ("oda", "numara", "tel", "no ")


def _normalized(options: tuple[str, ...], weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.get(option, 0.0) for option in options)
    return {option: round(weights.get(option, 0.0) / total, 6) for option in options}


def category_distribution(text: str) -> dict[str, float]:
    scores = score_categories(text)
    weights = {category.value: math.exp(1.2 * score) for category, score in scores.items()}
    weights[UNCLEAR] = math.exp(1.2 * 0.8)  # "hiçbiri/belirsiz" için sabit taban ağırlık
    return _normalized(CATEGORY_OPTIONS, weights)


def priority_distribution(text: str, data: DecisionInput) -> dict[str, float]:
    picked = pick_priority(text)
    if check_safety(data).flagged:
        picked = Priority.HIGH
    thin = len(words(normalize(text))) < 4
    on_picked = 0.45 if thin else 0.8
    rest = (1 - on_picked) / (len(PRIORITY_OPTIONS) - 1)
    weights = {option: rest for option in PRIORITY_OPTIONS}
    weights[picked.value] = on_picked
    return _normalized(PRIORITY_OPTIONS, weights)


def missing_probability(question: Question, data: DecisionInput) -> float:
    """Eksik olma olasılığı (evet) — yalnızca sahte ama tutarlı sezgiler."""
    flags = missing_flags(data)
    flagged = flags[question]
    if flagged is not None:
        return 0.92 if flagged else 0.04
    text = normalize(f"{data.title} {data.description}")
    if question is Question.MISSING_TIMING:
        return 0.1 if any(term in text for term in TIME_WORDS) else 0.7
    has_contact = any(char.isdigit() for char in text) or any(t in text for t in PHONE_OR_ROOM)
    return 0.2 if has_contact else 0.7


class MockProvider:
    prompt_version = "mock-1"

    def __init__(self, flavor: Flavor = "jev", script: list[CallStatus | None] | None = None):
        self.flavor = flavor
        self.name = f"mock-{flavor}"
        self.model = f"mock-{flavor}-1"
        self.price: PriceEntry = MOCK_JEV if flavor == "jev" else MOCK_LLM
        self.script = list(script or [])
        self.call_count = 0

    # --- kayıt ---

    def _record(
        self,
        strategy: StrategyName,
        questions: tuple[Question, ...],
        status: CallStatus,
        started: datetime,
        elapsed_s: float,
        data: DecisionInput,
        error: str | None = None,
    ) -> CallRecord:
        chars = len(data.title) + len(data.description) + len(data.location)
        ok = status is CallStatus.OK
        return CallRecord(
            strategy=strategy,
            provider=self.name,
            model=self.model,
            prompt_version=self.prompt_version,
            questions=questions,
            status=status,
            started_at=started,
            duration_ms=max(1, round(elapsed_s * 1000)),
            input_tokens=math.ceil(chars / 4) + 150 if ok else None,
            output_tokens=12 + 6 * len(questions) if ok else None,
            usage_estimated=ok,  # mock kullanım bildirmez; değerler tahmindir
            request_id=f"mock-{uuid4().hex[:12]}" if ok else None,
            error=error,
            is_mock=True,
        )

    # --- yargılar ---

    def _choice(self, question: Question, distribution: dict[str, float]) -> Judgment:
        answer = max(distribution, key=lambda option: distribution[option])
        p_max = distribution[answer]
        n = len(distribution)
        if self.flavor == "jev":
            confidence = max(0.0, (p_max - 1 / n) / (1 - 1 / n))
            return Judgment(
                question,
                answer,
                dict(distribution),
                round(confidence, 4),
                ConfidenceKind.JEV_CONFIDENCE,
                n,
                source=self.name,
            )
        return Judgment(
            question,
            answer,
            None,
            round(p_max, 2),
            ConfidenceKind.SELF_REPORTED,
            n,
            source=self.name,
        )

    def _yes_no(self, question: Question, p_yes: float) -> Judgment:
        answer = p_yes >= 0.5
        if self.flavor == "jev":
            return Judgment(
                question,
                answer,
                {"yes": p_yes, "no": round(1 - p_yes, 6)},
                round(abs(2 * p_yes - 1), 4),
                ConfidenceKind.DERIVED_MARGIN,
                2,
                source=self.name,
            )
        return Judgment(
            question,
            answer,
            None,
            round(max(p_yes, 1 - p_yes), 2),
            ConfidenceKind.SELF_REPORTED,
            2,
            source=self.name,
        )

    def classify(
        self, data: DecisionInput, questions: tuple[Question, ...], strategy: StrategyName
    ) -> ProviderResult:
        self.call_count += 1
        step = self.script.pop(0) if self.script else None
        started = datetime.now(UTC)
        t0 = time.perf_counter()

        if step is not None:
            raise ProviderError(
                step,
                f"mock hata: {step.value}",
                self._record(
                    strategy,
                    questions,
                    step,
                    started,
                    time.perf_counter() - t0,
                    data,
                    error=f"mock hata: {step.value}",
                ),
                retry_after=0.0 if step is CallStatus.RATE_LIMITED else None,
            )

        text = f"{data.title} {data.description}"
        judgments = []
        for question in questions:
            if question is Question.CATEGORY:
                judgments.append(self._choice(question, category_distribution(text)))
            elif question is Question.PRIORITY:
                judgments.append(self._choice(question, priority_distribution(text, data)))
            else:
                judgments.append(self._yes_no(question, missing_probability(question, data)))
        record = self._record(
            strategy, questions, CallStatus.OK, started, time.perf_counter() - t0, data
        )
        return ProviderResult(tuple(judgments), record)
