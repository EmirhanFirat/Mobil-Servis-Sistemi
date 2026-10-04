// Model karşılaştırma (yalnızca yönetici; kayıtlı deneyleri okur, hiçbir model çağrısı başlatmaz).
// Ücretler hassasiyet kaybı olmasın diye ondalık METİN olarak gelir; bilinmeyen değer null'dır
// (sıfır değildir). Şema: services/api/app/schemas_experiments.py (değişirse birlikte güncellenir).

import type { DecisionJudgment } from './types'

export type ExperimentStatus = 'complete' | 'partial' | 'missing_files' | 'corrupt'

export interface Proportion {
  successes: number
  n: number
  value: number | null
  wilson95: number[] | null
}

export interface ExperimentDataset {
  version: string | null
  sha256_short: string | null
  splits: string[]
  n_samples: number | null
  n_completed: number | null
  source: string | null
  label_status: string | null
  matches_current: boolean | null
}

export interface ProviderPart {
  provider: string | null
  model: string | null
  prompt_version: string | null
  temperature: number | null
}

export interface ExperimentStrategyInfo {
  name: string
  kind: string | null
  is_mock: boolean
  provider: string | null
  model: string | null
  prompt_version: string | null
  temperature: number | null
  jev: ProviderPart | null
  llm: ProviderPart | null
  thresholds: Record<string, number> | null
  escalate_on: string[] | null
  llm_min_self_reported: number | null
  routing_version: string | null
}

export interface HybridRouting {
  version: string
  /** false: kayıtta sürüm alanı yok → v1 sayıldı (eski yönlendirme). */
  recorded: boolean
  description: string
}

export interface ExperimentRun {
  id: string
  created_at: string | null
  source_commit: string | null
  git_dirty: boolean | null
  dataset: ExperimentDataset | null
  strategies: ExperimentStrategyInfo[]
  status: ExperimentStatus
  status_detail: string | null
  live: boolean
  hybrid_routing: HybridRouting | null
  scope_label: string | null
  files: { predictions: boolean; metrics: boolean; report: boolean }
}

export interface ExperimentList {
  runs_dir_found: boolean
  runs: ExperimentRun[]
}

export interface ExperimentMetrics {
  category_accuracy: Proportion
  category_macro_f1: number | null
  priority_accuracy: Proportion
  high_priority_recall: Proportion
  high_priority_missed: string[]
  review_rate: Proportion
  automated_rate: Proportion
  automated_category_accuracy: Proportion
  automated_priority_accuracy: Proportion
  latency_p50_ms: number | null
  latency_p95_ms: number | null
}

export interface ExperimentCost {
  known_usd: string
  calls_with_unknown_cost: number
  total_usd: string | null
  per_completed_usd: string | null
  /** TAHMİN: ölçülen talep başına ücretin 1.000 ile çarpımı; ölçülen toplam değildir. */
  estimate_per_1000_usd: string | null
}

export interface ProviderUsage {
  provider: string
  model: string
  is_mock: boolean
  calls: number
  retries: number
  call_errors: number
  input_tokens: number
  output_tokens: number
  calls_without_input_usage: number
  calls_without_output_usage: number
  usage_estimated_calls: number
  output_tokens_free: boolean
  cost_known_usd: string
  calls_with_unknown_cost: number
}

export interface ExperimentUsage {
  providers: ProviderUsage[]
  calls: number
  retries: number
  call_errors: number
  input_tokens: number
  output_tokens: number
  calls_without_usage: number
}

export interface HybridStats {
  escalated: Proportion
  trigger_questions: Record<string, number>
  jev_stage_calls: number
  llm_stage_calls: number
}

export interface StrategyResult {
  name: string
  info: ExperimentStrategyInfo
  n: number
  n_failed: number
  metrics: ExperimentMetrics
  cost: ExperimentCost
  usage: ExperimentUsage
  hybrid: HybridStats | null
}

export interface ExperimentPrice {
  provider: string | null
  model: string | null
  input_usd_per_mtok: string
  output_usd_per_mtok: string
  source_url: string | null
  checked_on: string | null
}

export interface ExperimentConditions {
  dataset_version: string | null
  splits: string[]
  shuffle_seed: number | null
  final: boolean
  limit: number | null
  concurrency: number | null
  retry_max_attempts: number | null
  strategies: ExperimentStrategyInfo[]
  prices: ExperimentPrice[]
  python: string | null
}

export interface ExperimentBudget {
  budget_id: string | null
  max_cost_usd: string | null
  known_spent_usd: string | null
  conservative_spent_usd: string | null
  conservative_charges: number | null
  calls: number | null
  prior_spent_usd: string | null
  prior_unresolved_reserved_usd: string | null
  total_spent_usd: string | null
  remaining_usd: string | null
}

export interface ExperimentReconciliation {
  compared_known_usd: string
  run_known_spent_usd: string
  outside_comparison_usd: string
  conservative_spent_usd: string | null
}

export interface ExperimentGold {
  category: string
  priority: string
  missing_info: string[]
  expected_review: boolean
}

export interface DisputedLabel {
  status: string
  note: string
}

export interface SampleCell {
  failed: boolean
  category: string | null
  priority: string | null
  category_ok: boolean | null
  priority_ok: boolean | null
  review_required: boolean | null
  latency_ms: number | null
  cost_known_usd: string
  calls_with_unknown_cost: number
}

export interface SampleRow {
  id: string
  title: string
  split: string
  variant: string
  tags: string[]
  gold: ExperimentGold
  disputed: DisputedLabel | null
  in_common: boolean
  strategies: Record<string, SampleCell | null>
}

export interface ExperimentWarning {
  code: string
  text: string
}

export interface ExperimentDetail {
  run: ExperimentRun
  metrics_available: boolean
  unavailable_reason: string | null
  conditions: ExperimentConditions | null
  budget: ExperimentBudget | null
  common: {
    n: number
    sample_ids: string[]
    excluded: { sample_id: string; missing_strategies: string[] }[]
  }
  strategies: StrategyResult[]
  reconciliation: ExperimentReconciliation | null
  samples: SampleRow[]
  warnings: ExperimentWarning[]
  notes: { comparability: string; tokens: string }
}

export interface SampleCall {
  provider: string | null
  model: string | null
  attempt: number | null
  status: string | null
  duration_ms: number | null
  input_tokens: number | null
  output_tokens: number | null
  usage_estimated: boolean | null
  cost_usd: string | null
  questions: string[] | null
  is_mock: boolean | null
}

export interface SampleStrategy {
  name: string
  info: ExperimentStrategyInfo
  present: boolean
  failed: boolean | null
  error: string | null
  category: string | null
  priority: string | null
  missing_info: string[]
  review_required: boolean | null
  review_reasons: string[]
  latency_ms: number | null
  is_mock: boolean | null
  providers: string[]
  model_versions: string[]
  category_ok: boolean | null
  priority_ok: boolean | null
  judgments: DecisionJudgment[]
  calls: SampleCall[]
  usage: ProviderUsage[]
  cost_known_usd: string | null
  calls_with_unknown_cost: number | null
  escalated_questions: string[]
}

export interface ExperimentSample {
  run_id: string
  sample: {
    id: string
    title: string
    description: string
    location: string
    split: string
    variant: string
    tags: string[]
    source: string
    label_status: string
    gold: ExperimentGold
    disputed: DisputedLabel | null
  }
  strategies: SampleStrategy[]
}
