"""Karar ve çağrı kayıtlarını JSON'a çevirir (predictions.jsonl). Rapor, bu kayıtlardan model
çağrısı yapmadan yeniden üretilebilir."""

from app.decision.contract import CallRecord, Decision, Judgment


def call_to_dict(call: CallRecord) -> dict:
    return {
        "call_id": str(call.call_id),
        "strategy": call.strategy.value,
        "provider": call.provider,
        "model": call.model,
        "prompt_version": call.prompt_version,
        "questions": [q.value for q in call.questions],
        "status": call.status.value,
        "attempt": call.attempt,
        "started_at": call.started_at.isoformat(),
        "duration_ms": call.duration_ms,
        "provider_duration_ms": call.provider_duration_ms,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "usage_estimated": call.usage_estimated,
        "cost_usd": None if call.cost_usd is None else str(call.cost_usd),
        "request_id": call.request_id,
        "error": call.error,
        "is_mock": call.is_mock,
    }


def judgment_to_dict(judgment: Judgment) -> dict:
    return {
        "question": judgment.question.value,
        "answer": judgment.answer,
        "probabilities": judgment.probabilities,
        "confidence": judgment.confidence,
        "confidence_kind": judgment.confidence_kind.value if judgment.confidence_kind else None,
        "n_options": judgment.n_options,
        "source": judgment.source,
        "adopted": judgment.adopted,
    }


def decision_to_dict(decision: Decision) -> dict:
    return {
        "decision_id": str(decision.decision_id),
        "decision_strategy": decision.strategy.value,
        "category": decision.category.value if decision.category else None,
        "priority": decision.priority.value if decision.priority else None,
        "missing_info": [m.value for m in decision.missing_info],
        "review_required": decision.review_required,
        "review_reasons": list(decision.review_reasons),
        "providers": list(decision.providers),
        "model_versions": list(decision.model_versions),
        "is_mock": decision.is_mock,
        "judgments": [judgment_to_dict(j) for j in decision.judgments],
        "calls": [call_to_dict(c) for c in decision.calls],
    }
