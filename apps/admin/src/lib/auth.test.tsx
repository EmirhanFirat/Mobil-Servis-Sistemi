import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from './auth'
import { ADMIN_ONLY_MESSAGE, useAuth } from './auth-context'
import { readStoredToken, setSessionToken, storeToken } from './session-token'
import type { Role, User } from './types'

const vocab = { roles: [], statuses: [], priorities: [], categories: [], teams: [], missing_info: [], category_default_team: {} }

function userWith(role: Role): User {
  return { id: '1', username: 'x', display_name: 'Zeynep', role, is_active: true, teams: [] }
}

type Route = () => Response | Promise<Response>

/** fetch'i yöntem+yol'a göre yönlendirir; tanımsız yol testi düşürür. */
function stubFetch(routes: Record<string, Route>) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname
    const handler = routes[`${init?.method ?? 'GET'} ${path}`]
    if (!handler) throw new Error(`Beklenmeyen istek: ${init?.method} ${path}`)
    return handler()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function Probe() {
  const auth = useAuth()
  const [failure, setFailure] = useState('')
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="notice">{auth.notice ?? ''}</span>
      <span data-testid="error">{auth.error?.name ?? ''}</span>
      <span data-testid="failure">{failure}</span>
      <button onClick={() => auth.signIn('x', 'y').catch((e: Error) => setFailure(e.message))}>giriş</button>
      <button onClick={auth.signOut}>çıkış</button>
    </div>
  )
}

const renderProvider = () =>
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )

const status = () => screen.getByTestId('status').textContent

beforeEach(() => {
  sessionStorage.clear()
  setSessionToken(null)
})
afterEach(() => vi.unstubAllGlobals())

describe('AuthProvider: giriş', () => {
  it('yönetici girişinde oturum açılır ve token sessionStorage’a yazılır', async () => {
    stubFetch({
      'POST /auth/login': () => json(200, { access_token: 'jeton-1', token_type: 'bearer', user: userWith('admin') }),
      'GET /meta/vocabulary': () => json(200, vocab),
    })
    const user = userEvent.setup()
    renderProvider()
    await waitFor(() => expect(status()).toBe('signedOut'))

    await user.click(screen.getByText('giriş'))

    await waitFor(() => expect(status()).toBe('signedIn'))
    expect(readStoredToken()).toBe('jeton-1')
  })

  it('yönetici olmayan hesap reddedilir ve token HİÇ saklanmaz', async () => {
    stubFetch({
      'POST /auth/login': () => json(200, { access_token: 'jeton-2', token_type: 'bearer', user: userWith('requester') }),
    })
    const user = userEvent.setup()
    renderProvider()
    await waitFor(() => expect(status()).toBe('signedOut'))

    await user.click(screen.getByText('giriş'))

    await waitFor(() => expect(screen.getByTestId('failure')).toHaveTextContent(ADMIN_ONLY_MESSAGE))
    expect(status()).toBe('signedOut')
    expect(readStoredToken()).toBeNull()
  })

  it('çıkış token’ı siler', async () => {
    storeToken('jeton-3')
    stubFetch({
      'GET /auth/me': () => json(200, userWith('admin')),
      'GET /meta/vocabulary': () => json(200, vocab),
    })
    const user = userEvent.setup()
    renderProvider()
    await waitFor(() => expect(status()).toBe('signedIn'))

    await user.click(screen.getByText('çıkış'))

    expect(status()).toBe('signedOut')
    expect(readStoredToken()).toBeNull()
  })
})

describe('AuthProvider: açılışta kayıtlı oturum', () => {
  it('geçerli yönetici oturumu sürdürülür', async () => {
    storeToken('jeton-4')
    stubFetch({
      'GET /auth/me': () => json(200, userWith('admin')),
      'GET /meta/vocabulary': () => json(200, vocab),
    })

    renderProvider()

    await waitFor(() => expect(status()).toBe('signedIn'))
  })

  it('kayıtlı token yönetici olmayan hesaba aitse oturum kapatılır ve açıklama gösterilir', async () => {
    storeToken('jeton-5')
    stubFetch({
      'GET /auth/me': () => json(200, userWith('technician')),
      'GET /meta/vocabulary': () => json(200, vocab),
    })

    renderProvider()

    await waitFor(() => expect(status()).toBe('signedOut'))
    expect(screen.getByTestId('notice')).toHaveTextContent(ADMIN_ONLY_MESSAGE)
    expect(readStoredToken()).toBeNull()
  })

  it('sunucu 401 verirse oturum sona erer, token silinir, uyarı gösterilir', async () => {
    storeToken('suresi-dolmus')
    stubFetch({
      'GET /auth/me': () => json(401, { detail: 'Oturum geçersiz', code: 'unauthorized' }),
      'GET /meta/vocabulary': () => json(200, vocab),
    })

    renderProvider()

    await waitFor(() => expect(status()).toBe('signedOut'))
    expect(screen.getByTestId('notice')).toHaveTextContent('Oturumun süresi doldu')
    expect(readStoredToken()).toBeNull()
  })

  it('sunucuya ulaşılamazsa çıkış yapmaz: hata durumuna geçer ve token’ı korur', async () => {
    storeToken('jeton-6')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderProvider()

    await waitFor(() => expect(status()).toBe('error'))
    expect(screen.getByTestId('error')).toHaveTextContent('NetworkError')
    expect(readStoredToken()).toBe('jeton-6')
  })

  it('token yoksa istek atmadan giriş ekranına düşer', async () => {
    const fetchMock = stubFetch({})

    renderProvider()

    await waitFor(() => expect(status()).toBe('signedOut'))
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
