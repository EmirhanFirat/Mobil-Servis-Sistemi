"""Metrikler. Saf fonksiyonlar; model çağrısı yapmaz, yalnızca kayıtlı tahminleri okur.

Yorum notları:
- Küçük örneklemde oranlar için Wilson güven aralığı verilir; aralıklar geniştir.
- İncelemeye bırakılan (otomatik karar vermeyen) örnekler başarı sayılmaz: "otomatik kararların
  doğruluğu" ve "otomasyon oranı" ayrıca raporlanır.
- Bilinmeyen maliyet sıfır sayılmaz: bilinen toplam ve bilinmeyen çağrı sayısı ayrı verilir.
- Token sayıları farklı tokenizer'lar yüzünden sağlayıcılar arasında tam eşdeğer değildir.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from app.decision.contract import UNCLEAR
from app.evaluation.dataset import (
    CATEGORY_LABELS,
    MISSING_LABELS,
    Sample,
)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Oran için Wilson güven aralığı (%95). n=0 ise None."""
    if n == 0:
        return None
    p = successes / n
    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def percentile(values: list[float], q: float) -> float | None:
    """Doğrusal enterpolasyonlu yüzdelik (q: 0–100). Boşsa None."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * q / 100
    low = math.floor(rank)
    high = math.ceil(rank)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


@dataclass(frozen=True)
class Proportion:
    successes: int
    n: int

    @property
    def value(self) -> float | None:
        return self.successes / self.n if self.n else None

    @property
    def interval(self) -> tuple[float, float] | None:
        return wilson_interval(self.successes, self.n)


@dataclass(frozen=True)
class ClassScore:
    precision: float | None
    recall: float | None
    f1: float | None
    support: int


def class_scores(
    gold: list[str], predicted: list[str], labels: tuple[str, ...]
) -> dict[str, ClassScore]:
    result: dict[str, ClassScore] = {}
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, predicted, strict=True))
        fp = sum(g != label and p == label for g, p in zip(gold, predicted, strict=True))
        fn = sum(g == label and p != label for g, p in zip(gold, predicted, strict=True))
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else (0.0 if tp + fp + fn else None)
        )
        result[label] = ClassScore(precision, recall, f1, tp + fn)
    return result


def macro_f1(scores: dict[str, ClassScore]) -> float | None:
    """Yalnızca altın etiketlerde bulunan (destek > 0) sınıfların ortalaması."""
    values = [s.f1 for s in scores.values() if s.support > 0 and s.f1 is not None]
    return sum(values) / len(values) if values else None


def confusion(
    gold: list[str], predicted: list[str], labels: tuple[str, ...]
) -> dict[str, dict[str, int]]:
    matrix = {g: dict.fromkeys(labels, 0) for g in labels}
    for g, p in zip(gold, predicted, strict=True):
        matrix[g][p] += 1
    return matrix


@dataclass
class Prediction:
    """Kayıtlı bir tahmin satırından okunan alanlar (predictions.jsonl)."""

    sample_id: str
    strategy: str
    failed: bool
    category: str | None
    priority: str | None
    missing_info: tuple[str, ...]
    review_required: bool
    review_reasons: tuple[str, ...]
    latency_ms: float | None
    is_mock: bool
    calls: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, row: dict) -> "Prediction":
        return cls(
            sample_id=row["sample_id"],
            strategy=row["strategy"],
            failed=bool(row["failed"]),
            category=row.get("category"),
            priority=row.get("priority"),
            missing_info=tuple(row.get("missing_info", [])),
            review_required=bool(row.get("review_required", False)),
            review_reasons=tuple(row.get("review_reasons", [])),
            latency_ms=row.get("latency_ms"),
            is_mock=bool(row.get("is_mock", False)),
            calls=list(row.get("calls", [])),
        )


@dataclass(frozen=True)
class StrategyMetrics:
    strategy: str
    n: int
    n_failed: int
    is_mock: bool
    category_accuracy: Proportion
    category_macro_f1: float | None
    category_scores: dict[str, ClassScore]
    category_confusion: dict[str, dict[str, int]]
    priority_accuracy: Proportion
    high_priority_recall: Proportion
    high_priority_missed: tuple[str, ...]
    review_rate: Proportion
    automated_category_accuracy: Proportion
    automated_priority_accuracy: Proportion
    review_precision: Proportion
    review_recall: Proportion
    missing_scores: dict[str, ClassScore]
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    calls_total: int
    calls_failed: int
    input_tokens_known: int
    output_tokens_known: int
    calls_without_usage: int
    cost_known_usd: Decimal
    calls_with_unknown_cost: int
    cost_per_decision_usd: Decimal | None
    cost_per_correct_usd: Decimal | None
    correct_automated: int
    by_tag: dict[str, Proportion]

    @property
    def failure_rate(self) -> Proportion:
        return Proportion(self.n_failed, self.n)

    @property
    def cost_total_usd(self) -> Decimal | None:
        """Bilinmeyen maliyetli çağrı varsa None (sıfır sayılmaz)."""
        return None if self.calls_with_unknown_cost else self.cost_known_usd


def compute_metrics(
    samples: dict[str, Sample], predictions: list[Prediction], strategy: str
) -> StrategyMetrics:
    rows = [(samples[p.sample_id], p) for p in predictions if p.strategy == strategy]
    ok = [(s, p) for s, p in rows if not p.failed]

    gold_cat = [s.gold.category for s, _ in ok]
    pred_cat = [p.category or UNCLEAR for _, p in ok]
    scores = class_scores(gold_cat, pred_cat, CATEGORY_LABELS)

    gold_pri = [s.gold.priority for s, _ in ok]
    pred_pri = [p.priority or UNCLEAR for _, p in ok]

    high = [(s, p) for s, p in ok if s.gold.priority == "high"]
    missed = tuple(s.id for s, p in high if p.priority != "high")

    automated = [(s, p) for s, p in ok if not p.review_required]
    flagged = [(s, p) for s, p in ok if p.review_required]
    expected = [(s, p) for s, p in ok if s.expected_review]

    missing_gold = {
        label: [label in s.gold.missing_info for s, _ in ok] for label in MISSING_LABELS
    }
    missing_pred = {label: [label in p.missing_info for _, p in ok] for label in MISSING_LABELS}
    missing_scores = {
        label: class_scores(
            ["yes" if v else "no" for v in missing_gold[label]],
            ["yes" if v else "no" for v in missing_pred[label]],
            ("yes",),
        )["yes"]
        for label in MISSING_LABELS
    }

    latencies = [p.latency_ms for _, p in ok if p.latency_ms is not None]

    all_calls = [call for _, p in rows for call in p.calls]
    known = Decimal(0)
    unknown = 0
    in_tok = out_tok = no_usage = 0
    for call in all_calls:
        cost = call.get("cost_usd")
        if cost is None:
            unknown += 1
        else:
            known += Decimal(cost)
        if call.get("input_tokens") is None:
            no_usage += 1
        else:
            in_tok += call["input_tokens"]
        out_tok += call.get("output_tokens") or 0

    correct_automated = sum(
        s.gold.category == (p.category or UNCLEAR) and s.gold.priority == (p.priority or UNCLEAR)
        for s, p in automated
    )

    tag_counts: dict[str, list[bool]] = {}
    for s, p in ok:
        correct = s.gold.category == (p.category or UNCLEAR)
        for tag in s.tags:
            tag_counts.setdefault(tag, []).append(correct)

    return StrategyMetrics(
        strategy=strategy,
        n=len(rows),
        n_failed=len(rows) - len(ok),
        is_mock=any(p.is_mock for _, p in rows),
        category_accuracy=Proportion(
            sum(g == p for g, p in zip(gold_cat, pred_cat, strict=True)), len(ok)
        ),
        category_macro_f1=macro_f1(scores),
        category_scores=scores,
        category_confusion=confusion(gold_cat, pred_cat, CATEGORY_LABELS),
        priority_accuracy=Proportion(
            sum(g == p for g, p in zip(gold_pri, pred_pri, strict=True)), len(ok)
        ),
        high_priority_recall=Proportion(len(high) - len(missed), len(high)),
        high_priority_missed=missed,
        review_rate=Proportion(len(flagged), len(ok)),
        automated_category_accuracy=Proportion(
            sum(s.gold.category == (p.category or UNCLEAR) for s, p in automated), len(automated)
        ),
        automated_priority_accuracy=Proportion(
            sum(s.gold.priority == (p.priority or UNCLEAR) for s, p in automated), len(automated)
        ),
        review_precision=Proportion(sum(s.expected_review for s, _ in flagged), len(flagged)),
        review_recall=Proportion(sum(p.review_required for _, p in expected), len(expected)),
        missing_scores=missing_scores,
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
        calls_total=len(all_calls),
        calls_failed=sum(call.get("status") != "ok" for call in all_calls),
        input_tokens_known=in_tok,
        output_tokens_known=out_tok,
        calls_without_usage=no_usage,
        cost_known_usd=known,
        calls_with_unknown_cost=unknown,
        cost_per_decision_usd=(known / len(ok)) if ok and not unknown else None,
        cost_per_correct_usd=(known / correct_automated)
        if correct_automated and not unknown
        else None,
        correct_automated=correct_automated,
        by_tag={tag: Proportion(sum(v), len(v)) for tag, v in sorted(tag_counts.items())},
    )


def count_by(values: list[str]) -> dict[str, int]:
    return dict(Counter(values))
