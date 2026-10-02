import { createContext, useContext } from 'react'

import type { ApiClient } from './api'
import type { User, Vocabulary } from './types'

export type AuthStatus = 'loading' | 'signedOut' | 'signedIn' | 'error'

export const ADMIN_ONLY_MESSAGE = 'Bu panel yalnızca yöneticiler içindir.'

export interface AuthValue {
  status: AuthStatus
  user: User | null
  vocab: Vocabulary | null
  api: ApiClient
  /** Giriş ekranında gösterilecek bilgi (ör. oturum süresi doldu). */
  notice: string | null
  /** Açılışta sunucuya ulaşılamadığında gösterilecek hata (türü korunur). */
  error: Error | null
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => void
  retry: () => void
}

export const AuthContext = createContext<AuthValue | null>(null)

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth, AuthProvider içinde kullanılmalı.')
  return value
}

/** Oturum açık sayfalarda kullanılır; kullanıcı ve sözlük kesinlikle doludur. */
export function useSession(): AuthValue & { user: User; vocab: Vocabulary } {
  const value = useAuth()
  if (!value.user || !value.vocab) throw new Error('Oturum açık değil.')
  return value as AuthValue & { user: User; vocab: Vocabulary }
}
