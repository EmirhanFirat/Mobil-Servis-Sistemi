// API sözleşmesinin (services/api/app/schemas.py) istemci tarafı karşılığı.
// apps/mobile/src/lib/types.ts ile aynı alanları paylaşır; sözleşme değişirse ikisi birlikte güncellenir.

export type Role = 'requester' | 'technician' | 'admin'
export type TicketStatus =
  | 'new'
  | 'needs_review'
  | 'assigned'
  | 'in_progress'
  | 'resolved'
  | 'closed'
export type Priority = 'low' | 'normal' | 'high'
export type Category = 'electrical' | 'plumbing' | 'it_network' | 'cleaning' | 'other'

export interface Team {
  id: string
  code: string
  name: string
}

export interface Person {
  id: string
  display_name: string
  role: Role
}

export interface TeamWithMembers extends Team {
  members: Person[]
}

export interface User {
  id: string
  username: string
  display_name: string
  role: Role
  is_active: boolean
  teams: Team[]
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface LabeledValue {
  code: string
  label: string
}

export interface Vocabulary {
  roles: LabeledValue[]
  statuses: LabeledValue[]
  priorities: LabeledValue[]
  categories: LabeledValue[]
  teams: LabeledValue[]
  missing_info: LabeledValue[]
  category_default_team: Record<string, string>
}

export interface TicketSummary {
  id: string
  number: number
  title: string
  location: string
  status: TicketStatus
  category: Category | null
  priority: Priority
  team: Team | null
  assignee: Person | null
  created_by: Person
  missing_info: string[]
  review_required: boolean
  created_at: string
  updated_at: string
}

export interface TicketEvent {
  id: number
  kind: string
  data: Record<string, unknown>
  created_at: string
  actor: Person | null
}

export type JobStatus = 'pending' | 'running' | 'succeeded' | 'failed'
export type JobOutcome =
  | 'decided'
  | 'skipped_not_new'
  | 'skipped_human_edit'
  | 'failed_provider'
  | 'failed_error'
  | 'failed_worker_lost'
export type ApplyOutcome = 'applied' | 'skipped_not_new' | 'skipped_human_edit'
export type DecisionStrategy = 'rule_based' | 'llm_only' | 'jev_only' | 'hybrid'

export interface DecisionJob {
  /** Çalıştırılan strateji adı (rule_based, mock_hybrid, ...). */
  strategy: string
  status: JobStatus
  outcome: JobOutcome | null
  attempts: number
  max_attempts: number
  last_error: string | null
  created_at: string
  finished_at: string | null
}

export interface DecisionJudgment {
  question: string
  answer: string | boolean | null
  probabilities: Record<string, number> | null
  confidence: number | null
  /** jev_confidence | derived_margin | self_reported: birbirine eşdeğer sayılmaz. */
  confidence_kind: string | null
  n_options: number | null
  source: string | null
  adopted: boolean
}

/** Karar motorunun İLK tahmini; talebin güncel alanlarından ayrıdır. */
export interface Decision {
  id: string
  strategy: DecisionStrategy
  job_strategy: string | null
  is_mock: boolean
  providers: string[]
  model_versions: string[]
  category: Category | null
  priority: Priority | null
  missing_info: string[]
  review_required: boolean
  review_reasons: string[]
  applied_outcome: ApplyOutcome
  applied_at: string | null
  created_at: string
  judgments: DecisionJudgment[]
  calls_total: number
  cost_known_usd: string | null
  calls_with_unknown_cost: number
}

export interface DecisionPanelData {
  job: DecisionJob | null
  decision: Decision | null
}

export interface TicketDetail extends TicketSummary {
  description: string
  allowed_transitions: TicketStatus[]
  can_assign: boolean
  can_edit: boolean
  events: TicketEvent[]
  /** Yalnızca yöneticiye döner (sunucu karar verir); diğer rollerde null. */
  decision?: DecisionPanelData | null
}

export interface TicketList {
  items: TicketSummary[]
  total: number
  limit: number
  offset: number
}

export interface ListParams {
  status?: TicketStatus[]
  limit?: number
  offset?: number
}

export interface AssignBody {
  team_id: string
  assignee_id?: string | null
  note?: string
}

/** Gönderilmeyen alan değişmez; category için null göndermek temizler. */
export interface TicketPatchBody {
  priority?: Priority
  category?: Category | null
  missing_info?: string[]
  note?: string
}

export interface NewUser {
  username: string
  display_name: string
  password: string
  role: Role
}

export interface UserPatchBody {
  display_name?: string
  role?: Role
  is_active?: boolean
}
