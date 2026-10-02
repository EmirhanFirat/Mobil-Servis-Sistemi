import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ADMIN_ONLY_MESSAGE, AuthContext, type AuthValue } from '../lib/auth-context'
import { fakeApi } from '../test-utils'
import LoginPage from './LoginPage'

function renderLogin(overrides: Partial<AuthValue> = {}) {
  const value: AuthValue = {
    status: 'signedOut',
    user: null,
    vocab: null,
    api: fakeApi(),
    notice: null,
    error: null,
    signIn: vi.fn().mockResolvedValue(undefined),
    signOut: vi.fn(),
    retry: vi.fn(),
    ...overrides,
  }
  render(
    <AuthContext.Provider value={value}>
      <LoginPage />
    </AuthContext.Provider>,
  )
  return { value, user: userEvent.setup() }
}

describe('LoginPage', () => {
  it('boş gönderimde istek atmadan uyarır', async () => {
    const { value, user } = renderLogin()

    await user.click(screen.getByRole('button', { name: 'Giriş yap' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Kullanıcı adı ve parolayı gir.')
    expect(value.signIn).not.toHaveBeenCalled()
  })

  it('kullanıcı adını kırpıp parolayı olduğu gibi gönderir', async () => {
    const { value, user } = renderLogin()

    await user.type(screen.getByLabelText('Kullanıcı adı'), '  yonetici ')
    await user.type(screen.getByLabelText('Parola'), 'gizli parola ')
    await user.click(screen.getByRole('button', { name: 'Giriş yap' }))

    await waitFor(() => expect(value.signIn).toHaveBeenCalledWith('yonetici', 'gizli parola '))
  })

  it('giriş reddedilince sunucunun mesajını gösterir ve yeniden denemeye izin verir', async () => {
    const signIn = vi.fn().mockRejectedValue(new Error('Kullanıcı adı veya parola hatalı.'))
    const { user } = renderLogin({ signIn })

    await user.type(screen.getByLabelText('Kullanıcı adı'), 'yonetici')
    await user.type(screen.getByLabelText('Parola'), 'yanlis')
    await user.click(screen.getByRole('button', { name: 'Giriş yap' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Kullanıcı adı veya parola hatalı.')
    expect(screen.getByRole('button', { name: 'Giriş yap' })).toBeEnabled()
  })

  it('yönetici olmayan hesap için yalnızca-yönetici mesajını gösterir', async () => {
    const signIn = vi.fn().mockRejectedValue(new Error(ADMIN_ONLY_MESSAGE))
    const { user } = renderLogin({ signIn })

    await user.type(screen.getByLabelText('Kullanıcı adı'), 'ayse')
    await user.type(screen.getByLabelText('Parola'), 'parola')
    await user.click(screen.getByRole('button', { name: 'Giriş yap' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(ADMIN_ONLY_MESSAGE)
  })

  it('oturum süresi doldu bilgisini gösterir', () => {
    renderLogin({ notice: 'Oturumun süresi doldu. Lütfen yeniden giriş yap.' })

    expect(screen.getByRole('status')).toHaveTextContent('Oturumun süresi doldu')
  })
})
