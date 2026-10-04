"""Model karşılaştırma uçlarının yanıt şemaları (yalnızca yönetici).

Şemalar BEYAZ LİSTEDİR: FastAPI `response_model` ile yalnızca burada adı geçen alanlar yanıta çıkar.
Bu, run.json'daki yerel dosya yolu (bütçe defteri yolu) gibi alanların sızmasını da önler.
Ücretler hassasiyet kaybı olmasın diye ondalık METİN olarak taşınır; bilinmeyen değer null'dır,
sıfır değildir.
"""

from typing import Literal

from pydantic import BaseModel

from app.schemas import JudgmentOut

RunStatus = Literal["complete", "partial", "missing_files", "corrupt"]


class PropOut(BaseModel):
    successes: int
    n: int
    value: float | None
    wilson95: list[float] | None


class DatasetOut(BaseModel):
    version: str | None
    sha256_short: str | None
    splits: list[str]
    n_samples: int | None
    n_completed: int | None
    source: str | None
    label_status: str | None
    matches_current: bool | None


class ProviderPartOut(BaseModel):
    provider: str | None
    model: str | None
    prompt_version: str | None
    temperature: float | None


class StrategyInfoOut(BaseModel):
    name: str
    kind: str | None
    is_mock: bool
    provider: str | None
    model: str | None
    prompt_version: str | None
    temperature: float | None
    jev: ProviderPartOut | None
    llm: ProviderPartOut | None
    thresholds: dict[str, float] | None
    escalate_on: list[str] | None
    llm_min_self_reported: float | None
    routing_version: str | None


class HybridRoutingOut(BaseModel):
    version: str
    recorded: bool  # False: kayıtta sürüm alanı yok → v1 sayıldı
    description: str


class FilesOut(BaseModel):
    predictions: bool
    metrics: bool
    report: bool


class RunSummaryOut(BaseModel):
    id: str
    created_at: str | None
    source_commit: str | None
    git_dirty: bool | None
    dataset: DatasetOut | None
    strategies: list[StrategyInfoOut]
    status: RunStatus
    status_detail: str | None
    live: bool
    hybrid_routing: HybridRoutingOut | None
    scope_label: str | None
    files: FilesOut


class RunListOut(BaseModel):
    runs_dir_found: bool
    runs: list[RunSummaryOut]


class MetricsOut(BaseModel):
    category_accuracy: PropOut
    category_macro_f1: float | None
    priority_accuracy: PropOut
    high_priority_recall: PropOut
    high_priority_missed: list[str]
    review_rate: PropOut
    automated_rate: PropOut
    automated_category_accuracy: PropOut
    automated_priority_accuracy: PropOut
    latency_p50_ms: float | None
    latency_p95_ms: float | None


class CostOut(BaseModel):
    known_usd: str
    calls_with_unknown_cost: int
    total_usd: str | None
    per_completed_usd: str | None
    estimate_per_1000_usd: str | None  # TAHMİN: ölçülen talep başına ücretin 1.000 ile çarpımı


class ProviderUsageOut(BaseModel):
    provider: str
    model: str
    is_mock: bool
    calls: int
    retries: int
    call_errors: int
    input_tokens: int
    output_tokens: int
    calls_without_input_usage: int
    calls_without_output_usage: int
    usage_estimated_calls: int
    output_tokens_free: bool
    cost_known_usd: str
    calls_with_unknown_cost: int


class UsageOut(BaseModel):
    providers: list[ProviderUsageOut]
    calls: int
    retries: int
    call_errors: int
    input_tokens: int
    output_tokens: int
    calls_without_usage: int


class HybridStatsOut(BaseModel):
    escalated: PropOut
    trigger_questions: dict[str, int]
    jev_stage_calls: int
    llm_stage_calls: int


class StrategyResultOut(BaseModel):
    name: str
    info: StrategyInfoOut
    n: int
    n_failed: int
    metrics: MetricsOut
    cost: CostOut
    usage: UsageOut
    hybrid: HybridStatsOut | None


class PriceOut(BaseModel):
    provider: str | None
    model: str | None
    input_usd_per_mtok: str
    output_usd_per_mtok: str
    source_url: str | None
    checked_on: str | None


class ConditionsOut(BaseModel):
    dataset_version: str | None
    splits: list[str]
    shuffle_seed: int | None
    final: bool
    limit: int | None
    concurrency: int | None
    retry_max_attempts: int | None
    strategies: list[StrategyInfoOut]
    prices: list[PriceOut]
    python: str | None


class BudgetOut(BaseModel):
    budget_id: str | None
    max_cost_usd: str | None
    known_spent_usd: str | None
    conservative_spent_usd: str | None
    conservative_charges: int | None
    calls: int | None
    prior_spent_usd: str | None
    prior_unresolved_reserved_usd: str | None
    total_spent_usd: str | None
    remaining_usd: str | None


class ReconciliationOut(BaseModel):
    compared_known_usd: str
    run_known_spent_usd: str
    outside_comparison_usd: str
    conservative_spent_usd: str | None


class ExcludedOut(BaseModel):
    sample_id: str
    missing_strategies: list[str]


class CommonOut(BaseModel):
    n: int
    sample_ids: list[str]
    excluded: list[ExcludedOut]


class GoldOut(BaseModel):
    category: str
    priority: str
    missing_info: list[str]
    expected_review: bool


class DisputedOut(BaseModel):
    status: str
    note: str


class SampleCellOut(BaseModel):
    failed: bool
    category: str | None
    priority: str | None
    category_ok: bool | None
    priority_ok: bool | None
    review_required: bool | None
    latency_ms: float | None
    cost_known_usd: str
    calls_with_unknown_cost: int


class SampleRowOut(BaseModel):
    id: str
    title: str
    split: str
    variant: str
    tags: list[str]
    gold: GoldOut
    disputed: DisputedOut | None
    in_common: bool
    strategies: dict[str, SampleCellOut | None]


class WarningOut(BaseModel):
    code: str
    text: str


class NotesOut(BaseModel):
    comparability: str
    tokens: str


class RunDetailOut(BaseModel):
    run: RunSummaryOut
    metrics_available: bool
    unavailable_reason: str | None
    conditions: ConditionsOut | None
    budget: BudgetOut | None
    common: CommonOut
    strategies: list[StrategyResultOut]
    reconciliation: ReconciliationOut | None
    samples: list[SampleRowOut]
    warnings: list[WarningOut]
    notes: NotesOut


class CallOut(BaseModel):
    provider: str | None
    model: str | None
    attempt: int | None
    status: str | None
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    usage_estimated: bool | None
    cost_usd: str | None
    questions: list[str] | None
    is_mock: bool | None


class SampleStrategyOut(BaseModel):
    name: str
    info: StrategyInfoOut
    present: bool
    failed: bool | None = None
    error: str | None = None
    category: str | None = None
    priority: str | None = None
    missing_info: list[str] = []
    review_required: bool | None = None
    review_reasons: list[str] = []
    latency_ms: float | None = None
    is_mock: bool | None = None
    providers: list[str] = []
    model_versions: list[str] = []
    category_ok: bool | None = None
    priority_ok: bool | None = None
    judgments: list[JudgmentOut] = []
    calls: list[CallOut] = []
    usage: list[ProviderUsageOut] = []
    cost_known_usd: str | None = None
    calls_with_unknown_cost: int | None = None
    escalated_questions: list[str] = []


class SampleOut(BaseModel):
    id: str
    title: str
    description: str
    location: str
    split: str
    variant: str
    tags: list[str]
    source: str
    label_status: str
    gold: GoldOut
    disputed: DisputedOut | None


class SampleDetailOut(BaseModel):
    run_id: str
    sample: SampleOut
    strategies: list[SampleStrategyOut]
