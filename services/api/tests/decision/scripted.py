"""Hibrit yönlendirme testleri için elle kurgulanan sahte sağlayıcılar.

`MockProvider` sezgisel olasılıklar üretir; güveni soru soru KONTROL etmek gerekince bu sınıflar
kullanılır. Ağ isteği yoktur, ücret yoktur (cost_usd=0). Gerçek model davranışını ÖLÇMEZLER.
"""

from decimal import Decimal

from app.decision.contract import (
    CATEGORY_OPTIONS,
    MISSING_QUESTIONS,
    PRIORITY_OPTIONS,
    CallRecord,
    CallStatus,
    ConfidenceKind,
    DecisionInput,
    Judgment,
    Question,
    StrategyName,
)
from app.decision.pricing import MOCK_JEV, MOCK_LLM
from app.decision.providers import ProviderError, ProviderResult

# Güvenin yüksek olduğu, bütün karar sorularında Jev'in eminlik gösterdiği taban cevaplar.
DEFAULT_ANSWERS: dict[Question, str | bool] = {
    Question.CATEGORY: "plumbing",
    Question.PRIORITY: "normal",
    Question.MISSING_LOCATION: False,
    Question.MISSING_DETAIL: False,
    Question.MISSING_CONTACT: True,
    Question.MISSING_TIMING: True,
}

CONFIDENT = dict.fromkeys(DEFAULT_ANSWERS, 0.95)


def _record(name: str, model: str, questions, strategy, status=CallStatus.OK) -> CallRecord:
    ok = status is CallStatus.OK
    return CallRecord(
        strategy=strategy,
        provider=name,
        model=model,
        prompt_version="scripted-1",
        questions=tuple(questions),
        status=status,
        duration_ms=1,
        input_tokens=100 if ok else None,
        output_tokens=10 if ok else None,
        cost_usd=Decimal(0) if ok else None,  # başarısız denemenin ücreti bilinmez (None)
    )


class ScriptedJev:
    """Jev gibi davranır: HER istenen soruya, verilen güvenle yanıt verir."""

    name = "jev"
    model = MOCK_JEV.model  # fiyat girdisiyle aynı model adı: yoksa ücret "bilinmiyor" sayılır
    prompt_version = "scripted-1"
    price = MOCK_JEV  # sıfır fiyat: başarılı çağrının ücreti 0, başarısızınki bilinmez

    def __init__(
        self,
        confidence: dict[Question, float] | None = None,
        answers: dict[Question, str | bool] | None = None,
        script: list[CallStatus | None] | None = None,
    ):
        self.confidence = {**CONFIDENT, **(confidence or {})}
        self.answers = {**DEFAULT_ANSWERS, **(answers or {})}
        self.script = list(script or [])
        self.calls: list[tuple[Question, ...]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def classify(
        self, data: DecisionInput, questions: tuple[Question, ...], strategy: StrategyName
    ) -> ProviderResult:
        self.calls.append(tuple(questions))
        step = self.script.pop(0) if self.script else None
        if step is not None:
            record = _record(self.name, self.model, questions, strategy, step)
            raise ProviderError(step, f"hata: {step.value}", record)
        judgments = []
        for question in questions:
            answer = self.answers[question]
            if question in (Question.CATEGORY, Question.PRIORITY):
                options = CATEGORY_OPTIONS if question is Question.CATEGORY else PRIORITY_OPTIONS
                judgments.append(
                    Judgment(
                        question,
                        answer,
                        {option: 1 / len(options) for option in options},
                        self.confidence[question],
                        ConfidenceKind.JEV_CONFIDENCE,
                        len(options),
                        source=self.name,
                    )
                )
            else:
                assert question in MISSING_QUESTIONS
                judgments.append(
                    Judgment(
                        question,
                        answer,
                        {"yes": 0.5, "no": 0.5},
                        self.confidence[question],
                        ConfidenceKind.DERIVED_MARGIN,
                        2,
                        source=self.name,
                    )
                )
        return ProviderResult(tuple(judgments), _record(self.name, self.model, questions, strategy))


class ScriptedLLM:
    """LLM gibi davranır: yalnızca SORULAN sorulara, kendi yazdığı güvenle yanıt verir."""

    name = "anthropic"
    model = MOCK_LLM.model
    prompt_version = "scripted-1"
    price = MOCK_LLM

    def __init__(
        self,
        answers: dict[Question, str | bool] | None = None,
        script: list[CallStatus | None] | None = None,
        self_reported: float = 0.9,
    ):
        self.answers = {**DEFAULT_ANSWERS, **(answers or {})}
        self.script = list(script or [])
        self.self_reported = self_reported
        self.calls: list[tuple[Question, ...]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def classify(
        self, data: DecisionInput, questions: tuple[Question, ...], strategy: StrategyName
    ) -> ProviderResult:
        self.calls.append(tuple(questions))
        step = self.script.pop(0) if self.script else None
        if step is not None:
            record = _record(self.name, self.model, questions, strategy, step)
            raise ProviderError(step, f"hata: {step.value}", record)
        judgments = tuple(
            Judgment(
                question,
                self.answers[question],
                None,
                self.self_reported,
                ConfidenceKind.SELF_REPORTED,
                2 if question in MISSING_QUESTIONS else None,
                source=self.name,
            )
            for question in questions
        )
        return ProviderResult(judgments, _record(self.name, self.model, questions, strategy))
