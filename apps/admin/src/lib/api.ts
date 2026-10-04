import type { ExperimentDetail, ExperimentList, ExperimentSample } from './experiment-types'
import type {
  AssignBody,
  ListParams,
  NewUser,
  TeamWithMembers,
  TicketDetail,
  TicketList,
  TicketPatchBody,
  TicketStatus,
  TokenResponse,
  User,
  UserPatchBody,
  Vocabulary,
} from './types'

/** Sunucu yanıt verdi ama istek reddedildi (4xx/5xx). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | null

  constructor(status: number, code: string | null, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** Sunucuya hiç ulaşılamadı (ağ yok, adres yanlış, zaman aşımı). */
export class NetworkError extends Error {
  readonly timedOut: boolean

  constructor(message: string, timedOut = false) {
    super(message)
    this.name = 'NetworkError'
    this.timedOut = timedOut
  }
}

export interface ClientOptions {
  baseUrl: string
  getToken: () => string | null
  /** Kimlik gerektiren bir istek 401 alınca çağrılır (oturum süresi dolmuş/geçersiz). */
  onUnauthorized?: () => void
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

type Query = Record<string, string | number | string[] | undefined>

interface RequestOptions {
  body?: unknown
  query?: Query
  authenticated?: boolean
}

const FALLBACK_MESSAGES: Record<number, string> = {
  401: 'Oturum gerekli. Lütfen giriş yap.',
  403: 'Bu işlem için yetkin yok.',
  404: 'Kayıt bulunamadı.',
  409: 'İşlem şu anki duruma uygun değil.',
  422: 'Girilen bilgiler geçersiz. Alanları kontrol et.',
}

export function messageFromBody(
  status: number,
  body: unknown,
): { code: string | null; message: string } {
  // 5xx: sunucu iç hata metni (istisna izi vb.) kullanıcıya gösterilmez.
  if (status >= 500) {
    // Tek istisna: sunucunun bilinen, güvenli "veritabanına ulaşılamıyor" yanıtı. Metin sunucudan
    // alınmaz, istemcide sabittir; böylece kullanıcı "zaman aşımı" yerine gerçek durumu görür.
    const code = body && typeof body === 'object' ? (body as { code?: unknown }).code : null
    if (status === 503 && code === 'database_unavailable') {
      return { code, message: 'Sunucu şu anda veritabanına ulaşamıyor. Biraz sonra tekrar dene.' }
    }
    return { code: null, message: 'Sunucuda bir sorun oluştu. Biraz sonra tekrar dene.' }
  }
  if (body && typeof body === 'object') {
    const { detail, code } = body as { detail?: unknown; code?: unknown }
    const codeText = typeof code === 'string' ? code : null
    // İş kuralı hataları Türkçe düz metin döner; doğrulama hataları (422) liste döner.
    if (typeof detail === 'string' && detail.length > 0) return { code: codeText, message: detail }
  }
  return { code: null, message: FALLBACK_MESSAGES[status] ?? `İstek başarısız oldu (${status}).` }
}

function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const params: string[] = []
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined) continue
    for (const item of Array.isArray(value) ? value : [value]) {
      params.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(item))}`)
    }
  }
  return params.length > 0 ? `${path}?${params.join('&')}` : path
}

export function createApiClient(options: ClientOptions) {
  const { baseUrl, getToken, onUnauthorized, timeoutMs = 15000 } = options
  const fetchImpl = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args))

  async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
    const { body, query, authenticated = true } = opts
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (authenticated) {
      const token = getToken()
      if (token) headers.Authorization = `Bearer ${token}`
    }

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    let response: Response
    try {
      response = await fetchImpl(`${baseUrl}${withQuery(path, query)}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      })
    } catch {
      const timedOut = controller.signal.aborted
      throw new NetworkError(
        timedOut
          ? 'Sunucu zamanında yanıt vermedi.'
          : 'Sunucuya ulaşılamıyor. Bağlantını ve sunucu adresini kontrol et.',
        timedOut,
      )
    } finally {
      clearTimeout(timer)
    }

    let payload: unknown = null
    if (response.status !== 204) {
      try {
        payload = await response.json()
      } catch {
        payload = null // gövde JSON değil (ör. ara sunucu hata sayfası)
      }
    }

    if (!response.ok) {
      const { code, message } = messageFromBody(response.status, payload)
      if (response.status === 401 && authenticated) onUnauthorized?.()
      throw new ApiError(response.status, code, message)
    }
    return payload as T
  }

  const id = encodeURIComponent

  return {
    login: (username: string, password: string) =>
      request<TokenResponse>('POST', '/auth/login', {
        body: { username, password },
        authenticated: false,
      }),
    me: () => request<User>('GET', '/auth/me'),
    vocabulary: () => request<Vocabulary>('GET', '/meta/vocabulary', { authenticated: false }),

    listTickets: (params: ListParams = {}) =>
      request<TicketList>('GET', '/tickets', {
        query: { status: params.status, limit: params.limit, offset: params.offset },
      }),
    getTicket: (ticketId: string) => request<TicketDetail>('GET', `/tickets/${id(ticketId)}`),
    transition: (ticketId: string, to: TicketStatus, note?: string) =>
      request<TicketDetail>('POST', `/tickets/${id(ticketId)}/transitions`, {
        body: note ? { to, note } : { to },
      }),
    assign: (ticketId: string, body: AssignBody) =>
      request<TicketDetail>('POST', `/tickets/${id(ticketId)}/assignment`, { body }),
    patchTicket: (ticketId: string, body: TicketPatchBody) =>
      request<TicketDetail>('PATCH', `/tickets/${id(ticketId)}`, { body }),

    // Model karşılaştırma: yalnızca GET; kayıtlı deneyleri okur, hiçbir model çağrısı başlatmaz.
    listExperiments: () => request<ExperimentList>('GET', '/admin/experiments'),
    getExperiment: (runId: string) =>
      request<ExperimentDetail>('GET', `/admin/experiments/${id(runId)}`),
    getExperimentSample: (runId: string, sampleId: string) =>
      request<ExperimentSample>('GET', `/admin/experiments/${id(runId)}/samples/${id(sampleId)}`),

    listUsers: () => request<User[]>('GET', '/admin/users'),
    createUser: (body: NewUser) => request<User>('POST', '/admin/users', { body }),
    patchUser: (userId: string, body: UserPatchBody) =>
      request<User>('PATCH', `/admin/users/${id(userId)}`, { body }),
    listTeams: () => request<TeamWithMembers[]>('GET', '/admin/teams'),
    addMember: (teamId: string, userId: string) =>
      request<null>('PUT', `/admin/teams/${id(teamId)}/members/${id(userId)}`),
    removeMember: (teamId: string, userId: string) =>
      request<null>('DELETE', `/admin/teams/${id(teamId)}/members/${id(userId)}`),
  }
}

export type ApiClient = ReturnType<typeof createApiClient>
