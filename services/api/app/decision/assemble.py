"""Yargılardan nihai Decision üretir. Tüm stratejilerin ortak son adımıdır; güvenlik kapısı ve
inceleme gereksinimi kuralları burada, deterministik kodla uygulanır."""

from uuid import uuid4

from app.decision.contract import (
    CATEGORY_OPTIONS,
    MISSING_QUESTIONS,
    PRIORITY_OPTIONS,
    UNCLEAR,
    CallRecord,
    Decision,
    DecisionInput,
    Judgment,
    Question,
    StrategyName,
)
from app.decision.injection import looks_like_injection
from app.decision.safety import check_safety
from app.domain.vocabulary import Category, MissingInfo, Priority

# Bu bilgiler eksikse ekip talebi işleyemez; insan önce tamamlatmalı.
BLOCKING_MISSING = frozenset({MissingInfo.LOCATION, MissingInfo.DETAIL})

_PRIORITY_RANK = {Priority.LOW: 0, Priority.NORMAL: 1, Priority.HIGH: 2}


def _option(judgment: Judgment | None, options: tuple[str, ...]) -> str | None:
    """Geçerli bir seçenekse kodu, belirsiz/geçersiz/eksikse None döndürür."""
    if judgment is None or not isinstance(judgment.answer, str):
        return None
    if judgment.answer == UNCLEAR or judgment.answer not in options:
        return None
    return judgment.answer


def assemble(
    *,
    strategy: StrategyName,
    data: DecisionInput,
    judgments: list[Judgment],
    calls: list[CallRecord],
    providers: tuple[str, ...],
    model_versions: tuple[str, ...],
    extra_reasons: tuple[str, ...] = (),
) -> Decision:
    # Yalnızca benimsenen yargılar karara girer (hibritte Jev'in reddedilen yargısı kayıtta kalır).
    by_question = {j.question: j for j in judgments if j.adopted}

    category_code = _option(by_question.get(Question.CATEGORY), CATEGORY_OPTIONS)
    priority_code = _option(by_question.get(Question.PRIORITY), PRIORITY_OPTIONS)
    category = Category(category_code) if category_code else None
    priority = Priority(priority_code) if priority_code else None

    flagged = {
        MISSING_QUESTIONS[question]
        for question, judgment in by_question.items()
        if question in MISSING_QUESTIONS and judgment.answer is True
    }
    missing = tuple(label for label in MissingInfo if label in flagged)  # kararlı sıra

    reasons = list(extra_reasons)
    if category is None:
        reasons.append("category_unclear")
    if priority is None:
        reasons.append("priority_unclear")
    reasons.extend(f"{label.value}_missing" for label in missing if label in BLOCKING_MISSING)

    # Talimat enjeksiyonu şüphesi: model yönlendirilmeye çalışılmış olabilir; insan görsün.
    if looks_like_injection(data):
        reasons.append("possible_prompt_injection")

    # Güvenlik kapısı: strateji ne derse desin.
    safety = check_safety(data)
    if safety.flagged:
        reasons.extend(f"safety:{term}" for term in safety.terms)
        if priority is None or _PRIORITY_RANK[priority] < _PRIORITY_RANK[Priority.HIGH]:
            priority = Priority.HIGH

    return Decision(
        decision_id=uuid4(),
        strategy=strategy,
        category=category,
        priority=priority,
        missing_info=missing,
        review_required=bool(reasons),
        review_reasons=tuple(reasons),
        judgments=tuple(judgments),
        calls=tuple(calls),
        providers=providers,
        model_versions=model_versions,
        is_mock=any(call.is_mock for call in calls),
    )
