/** Canlı demo uçlarının yanıt sözleşmesi (services/api/app/schemas_demo.py ile aynı). */

export interface DemoLimits {
  title_max: number
  description_max: number
  location_max: number
  decisions_per_session: number
  session_minutes: number
}

export type DemoUnavailableReason = 'disabled' | 'not_configured' | 'budget_exhausted'

export interface DemoStatus {
  api_ready: boolean
  database_ready: boolean
  /** Veritabanının uyanma/sorgu süresi (ms); yalnızca hazırlık isteğinde ölçülür. */
  database_ms: number | null
  enabled: boolean
  reason: DemoUnavailableReason | null
  provider: string | null
  model: string | null
  is_mock: boolean
  limits: DemoLimits
  retention_hours: number
}

export interface DemoSession {
  access_token: string
  token_type: string
  expires_in_s: number
  decisions_total: number
  limits: DemoLimits
}

export type DemoState = 'pending' | 'running' | 'completed' | 'skipped' | 'failed' | 'uncertain' | 'budget_exhausted'

export interface DemoJudgment {
  question: string
  answer: string | boolean | null
  confidence: number | null
  /** jev_confidence (Jev'in verdiği) | derived_margin (bizim türettiğimiz): aynı şey değil. */
  confidence_kind: string | null
  adopted: boolean
}

export interface DemoDecisionInfo {
  category: string | null
  priority: string | null
  missing_info: string[]
  review_required: boolean
  review_explanations: string[]
  applied: boolean
  applied_outcome: string
  is_mock: boolean
  provider: string | null
  model: string | null
  judgments: DemoJudgment[]
}

export interface DemoUsage {
  calls: number
  input_tokens: number | null
  output_tokens: number | null
  output_tokens_free: boolean
  /** USD (metin). Bilinmiyorsa null ve cost_basis 'unknown': sıfır DEĞİL. */
  cost_usd: string | null
  cost_basis: 'provider_usage' | 'unknown'
  price_note: string
}

export interface DemoTimings {
  jev_call_ms: number | null
  job_ms: number | null
  server_total_ms: number | null
}

export interface DemoDecisionResult {
  ticket_id: string
  ticket_number: number
  state: DemoState
  message: string
  title: string
  description: string
  location: string
  ticket_status: string
  created_at: string
  decision: DemoDecisionInfo | null
  usage: DemoUsage | null
  timings: DemoTimings
  retry_after_s: number | null
  decisions_remaining: number
}

export interface DemoDecisionSummary {
  ticket_id: string
  ticket_number: number
  title: string
  state: DemoState
  created_at: string
}

export interface DemoDecisionInput {
  title: string
  description: string
  location: string
}
