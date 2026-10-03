import { describe, expect, it, vi } from 'vitest'

import { ApiError, NetworkError, createApiClient, messageFromBody } from './api'

type Call = { url: string; init: RequestInit }

function json(status: number, body: unknown): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function setup(respond: (call: Call) => Response | Promise<Response>, token: string | null = 'jeton') {
  const calls: Call[] = []
  const onUnauthorized = vi.fn()
  const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
    const call = { url, init }
    calls.push(call)
    return respond(call)
  }) as unknown as typeof fetch
  const api = createApiClient({
    baseUrl: 'http://api.test',
    getToken: () => token,
    onUnauthorized,
    fetchImpl,
    timeoutMs: 50,
  })
  return { api, calls, onUnauthorized }
}

const headersOf = (call: Call) => call.init.headers as Record<string, string>

describe('istek biçimi', () => {
  it('kimlik gerektiren isteklerde Authorization gönderir; girişte ve sözlükte göndermez', async () => {
    const { api, calls } = setup(() => json(200, {}))

    await api.listUsers()
    await api.login('yonetici', 'parola')
    await api.vocabulary()

    expect(headersOf(calls[0]).Authorization).toBe('Bearer jeton')
    expect(headersOf(calls[1]).Authorization).toBeUndefined()
    expect(headersOf(calls[2]).Authorization).toBeUndefined()
  })

  it('talep listesi sorgusunu kurar (tekrarlı durum, tanımsızları atlar)', async () => {
    const { api, calls } = setup(() => json(200, { items: [], total: 0, limit: 25, offset: 0 }))

    await api.listTickets({ status: ['new', 'needs_review'], limit: 25, offset: 50 })
    await api.listTickets()

    expect(calls[0].url).toBe('http://api.test/tickets?status=new&status=needs_review&limit=25&offset=50')
    expect(calls[1].url).toBe('http://api.test/tickets')
  })

  it('atama, düzeltme ve geçiş uçlarına doğru yol ve gövde gider', async () => {
    const { api, calls } = setup(() => json(200, {}))

    await api.assign('t1', { team_id: 'e', assignee_id: null, note: 'acil' })
    await api.patchTicket('t1', { priority: 'high', category: null })
    await api.transition('t1', 'closed')
    await api.transition('t1', 'closed', 'Yinelenen talep')

    expect(calls.map((c) => `${c.init.method} ${c.url}`)).toEqual([
      'POST http://api.test/tickets/t1/assignment',
      'PATCH http://api.test/tickets/t1',
      'POST http://api.test/tickets/t1/transitions',
      'POST http://api.test/tickets/t1/transitions',
    ])
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ team_id: 'e', assignee_id: null, note: 'acil' })
    // category: null "temizle" demektir; JSON'a null olarak gitmeli (alan düşmemeli)
    expect(JSON.parse(calls[1].init.body as string)).toEqual({ priority: 'high', category: null })
    expect(JSON.parse(calls[2].init.body as string)).toEqual({ to: 'closed' })
    expect(JSON.parse(calls[3].init.body as string)).toEqual({ to: 'closed', note: 'Yinelenen talep' })
  })

  it('kimlikleri adrese eklerken kodlar', async () => {
    const { api, calls } = setup(() => json(200, {}))

    await api.getTicket('a/b?c')

    expect(calls[0].url).toBe('http://api.test/tickets/a%2Fb%3Fc')
  })

  it('204 yanıtlı üyelik uçları hata vermez', async () => {
    const { api, calls } = setup(() => new Response(null, { status: 204 }))

    await expect(api.addMember('team', 'user')).resolves.toBeNull()
    await expect(api.removeMember('team', 'user')).resolves.toBeNull()

    expect(calls.map((c) => `${c.init.method} ${c.url}`)).toEqual([
      'PUT http://api.test/admin/teams/team/members/user',
      'DELETE http://api.test/admin/teams/team/members/user',
    ])
  })
})

describe('hata dönüşümü', () => {
  it('sunucunun Türkçe mesajını ve kodunu korur', async () => {
    const { api } = setup(() =>
      json(409, { detail: 'Bu görevlinin ekipte açık işi var.', code: 'has_open_tickets' }),
    )

    const error = await api.removeMember('t', 'u').catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(409)
    expect(error.code).toBe('has_open_tickets')
    expect(error.message).toBe('Bu görevlinin ekipte açık işi var.')
  })

  it('doğrulama hatasında (liste) genel Türkçe mesaj verir', () => {
    expect(messageFromBody(422, { detail: [{ msg: 'x' }] }).message).toBe(
      'Girilen bilgiler geçersiz. Alanları kontrol et.',
    )
  })

  it('5xx için sunucunun ham metnini göstermez', () => {
    expect(messageFromBody(500, { detail: 'Traceback ...' }).message).toBe(
      'Sunucuda bir sorun oluştu. Biraz sonra tekrar dene.',
    )
  })

  it('veritabanı yok (503 database_unavailable) yanıtını açıkça söyler; metni sunucudan almaz', () => {
    const result = messageFromBody(503, {
      detail: 'Traceback ... password=hunter2',
      code: 'database_unavailable',
    })

    expect(result).toEqual({
      code: 'database_unavailable',
      message: 'Sunucu şu anda veritabanına ulaşamıyor. Biraz sonra tekrar dene.',
    })
    expect(result.message).not.toContain('hunter2')
  })

  it('başka 503 (ve başka kodlu 5xx) genel mesaj verir', () => {
    const generic = 'Sunucuda bir sorun oluştu. Biraz sonra tekrar dene.'

    expect(messageFromBody(503, { detail: 'x', code: 'baska_kod' }).message).toBe(generic)
    expect(messageFromBody(503, null).message).toBe(generic)
    expect(messageFromBody(500, { code: 'database_unavailable' }).message).toBe(generic)
  })

  it('JSON olmayan hata gövdesinde de çökmez', async () => {
    const { api } = setup(() => new Response('<html>Bad Gateway</html>', { status: 502 }))

    const error = await api.me().catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(502)
  })
})

describe('oturum süresi (401)', () => {
  it('kimlik gerektiren istekte onUnauthorized çağrılır', async () => {
    const { api, onUnauthorized } = setup(() => json(401, { detail: 'Oturum geçersiz' }))

    await expect(api.listUsers()).rejects.toBeInstanceOf(ApiError)

    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('yanlış parolayla giriş (401) oturum sonlandırma sayılmaz', async () => {
    const { api, onUnauthorized } = setup(() =>
      json(401, { detail: 'Kullanıcı adı veya parola hatalı.', code: 'unauthorized' }),
    )

    const error = await api.login('yonetici', 'yanlış').catch((e) => e)

    expect(error.message).toBe('Kullanıcı adı veya parola hatalı.')
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

describe('ağ hataları', () => {
  it('bağlantı yoksa NetworkError (ApiError değil) fırlatır', async () => {
    const { api } = setup(() => {
      throw new TypeError('Failed to fetch')
    })

    const error = await api.me().catch((e) => e)

    expect(error).toBeInstanceOf(NetworkError)
    expect(error).not.toBeInstanceOf(ApiError)
    expect(error.timedOut).toBe(false)
  })

  it('zaman aşımında isteği iptal eder ve timedOut işaretler', async () => {
    const { api } = setup(
      ({ init }) =>
        new Promise<Response>((_, reject) => {
          init.signal?.addEventListener('abort', () => reject(new Error('aborted')))
        }),
    )

    const error = await api.me().catch((e) => e)

    expect(error).toBeInstanceOf(NetworkError)
    expect(error.timedOut).toBe(true)
  })
})
