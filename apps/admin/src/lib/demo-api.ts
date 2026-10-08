import { createRequester, type ClientOptions } from './api'
import type { DemoDecisionInput, DemoDecisionResult, DemoDecisionSummary, DemoSession, DemoStatus } from './demo-types'

/**
 * Canlı demo istemcisi. Hazırlık ve oturum uçları kimliksizdir; karar uçları ziyaretçi oturumunun
 * kısa ömürlü belirtecini kullanır. Karar isteğinin süresi, sunucunun tek denemelik Jev çağrısının
 * zaman aşımından (15 sn) uzun tutulur: istemci sunucudan önce vazgeçmesin.
 */
export const STATUS_TIMEOUT_MS = 30_000
export const DECISION_TIMEOUT_MS = 45_000

export function createDemoClient(options: ClientOptions) {
  const request = createRequester(options)
  const id = encodeURIComponent

  return {
    /** Model çağrısı YAPMAZ; ücretsiz sunucuyu ve veritabanını uyandırır. */
    status: (timeoutMs: number = STATUS_TIMEOUT_MS) =>
      request<DemoStatus>('GET', '/demo/status', { authenticated: false, timeoutMs }),
    openSession: () => request<DemoSession>('POST', '/demo/session', { authenticated: false }),
    decide: (body: DemoDecisionInput) =>
      request<DemoDecisionResult>('POST', '/demo/decisions', { body, timeoutMs: DECISION_TIMEOUT_MS }),
    /** Yalnızca okur; hiçbir koşulda model çağrısı başlatmaz. */
    getDecision: (ticketId: string) => request<DemoDecisionResult>('GET', `/demo/decisions/${id(ticketId)}`),
    listDecisions: () => request<DemoDecisionSummary[]>('GET', '/demo/decisions'),
  }
}

export type DemoClient = ReturnType<typeof createDemoClient>

/** Ziyaretçi belirteci: yalnızca bu sekmede (sessionStorage); kapanınca silinir. */
const TOKEN_KEY = 'talepakis.demo.token'
let memoryToken: string | null = null

export function readDemoToken(): string | null {
  if (memoryToken) return memoryToken
  try {
    memoryToken = globalThis.sessionStorage?.getItem(TOKEN_KEY) ?? null
  } catch {
    memoryToken = null
  }
  return memoryToken
}

export function storeDemoToken(token: string | null): void {
  memoryToken = token
  try {
    if (token) globalThis.sessionStorage?.setItem(TOKEN_KEY, token)
    else globalThis.sessionStorage?.removeItem(TOKEN_KEY)
  } catch {
    // Depo kullanılamıyorsa oturum yalnızca bu sayfa açıkken geçerli kalır.
  }
}
