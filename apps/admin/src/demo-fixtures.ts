import { vi } from 'vitest'

import type { DemoClient } from './lib/demo-api'
import type { DemoDecisionResult, DemoDecisionSummary, DemoLimits, DemoSession, DemoStatus } from './lib/demo-types'

export function makeLimits(): DemoLimits {
  return { title_max: 120, description_max: 1000, location_max: 120, decisions_per_session: 5, session_minutes: 180 }
}

export function makeStatus(overrides: Partial<DemoStatus> = {}): DemoStatus {
  return {
    api_ready: true,
    database_ready: true,
    database_ms: 120,
    enabled: true,
    reason: null,
    provider: 'jev',
    model: 'jev-1.13.0',
    is_mock: false,
    limits: makeLimits(),
    retention_hours: 72,
    ...overrides,
  }
}

export function makeSession(): DemoSession {
  return {
    access_token: 'demo-belirteci',
    token_type: 'bearer',
    expires_in_s: 10800,
    decisions_total: 5,
    limits: makeLimits(),
  }
}

export function makeResult(overrides: Partial<DemoDecisionResult> = {}): DemoDecisionResult {
  return {
    ticket_id: 'ticket-1',
    ticket_number: 7,
    state: 'completed',
    message: 'Jev kararı üretildi.',
    title: 'Lavabo akıtıyor',
    description: 'B blok ikinci kattaki ortak lavabo akıtıyor, su koridora yayılıyor.',
    location: 'B Blok, 2. kat',
    ticket_status: 'assigned',
    created_at: '2026-10-08T10:00:00+00:00',
    decision: {
      category: 'plumbing',
      priority: 'high',
      missing_info: ['contact'],
      review_required: false,
      review_explanations: [],
      applied: true,
      applied_outcome: 'applied',
      is_mock: false,
      provider: 'jev',
      model: 'jev-1.13.0',
      judgments: [
        {
          question: 'category',
          answer: 'plumbing',
          confidence: 0.88,
          confidence_kind: 'jev_confidence',
          adopted: true,
        },
        { question: 'priority', answer: 'high', confidence: 0.7, confidence_kind: 'jev_confidence', adopted: true },
        {
          question: 'missing_contact',
          answer: true,
          confidence: 0.6,
          confidence_kind: 'derived_margin',
          adopted: true,
        },
      ],
    },
    usage: {
      calls: 1,
      input_tokens: 392,
      output_tokens: 65,
      output_tokens_free: true,
      cost_usd: '0.000016464',
      cost_basis: 'provider_usage',
      price_note: 'Jev (jev-1.13.0): 0,042 USD / 1 milyon GİRDİ tokenı; çıktı tokenları ücretsiz.',
    },
    timings: { jev_call_ms: 481, job_ms: 520, server_total_ms: 700 },
    retry_after_s: null,
    decisions_remaining: 4,
    ...overrides,
  }
}

export function makeSummary(overrides: Partial<DemoDecisionSummary> = {}): DemoDecisionSummary {
  return {
    ticket_id: 'ticket-1',
    ticket_number: 7,
    title: 'Lavabo akıtıyor',
    state: 'completed',
    created_at: '2026-10-08T10:00:00+00:00',
    ...overrides,
  }
}

/** Her uç bir vi.fn()'dir; varsayılan olarak hazır sunucu ve başarılı karar döner. */
export function fakeDemoClient(overrides: Partial<Record<keyof DemoClient, unknown>> = {}): DemoClient {
  return {
    status: vi.fn().mockResolvedValue(makeStatus()),
    openSession: vi.fn().mockResolvedValue(makeSession()),
    decide: vi.fn().mockResolvedValue(makeResult()),
    getDecision: vi.fn().mockResolvedValue(makeResult()),
    listDecisions: vi.fn().mockResolvedValue([]),
    ...overrides,
  } as unknown as DemoClient
}
