import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { NetworkError, createApiClient } from './api'
import { ADMIN_ONLY_MESSAGE, AuthContext, type AuthStatus } from './auth-context'
import { API_URL } from './config'
import { getSessionToken, readStoredToken, setSessionToken, storeToken } from './session-token'
import type { User, Vocabulary } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [vocab, setVocab] = useState<Vocabulary | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [attempt, setAttempt] = useState(0)

  const endSession = useCallback((message: string | null) => {
    setSessionToken(null)
    storeToken(null)
    setUser(null)
    setVocab(null)
    setNotice(message)
    setStatus('signedOut')
  }, [])

  const api = useMemo(
    () =>
      createApiClient({
        baseUrl: API_URL,
        getToken: getSessionToken,
        onUnauthorized: () => endSession('Oturumun süresi doldu. Lütfen yeniden giriş yap.'),
      }),
    [endSession],
  )

  // Açılışta kayıtlı oturumu doğrula. Sunucuya ulaşılamıyorsa çıkış yapmak yerine hata göster.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      const token = readStoredToken()
      if (!token) {
        setStatus('signedOut')
        return
      }
      setStatus('loading')
      setSessionToken(token)
      try {
        const [me, vocabulary] = await Promise.all([api.me(), api.vocabulary()])
        if (cancelled) return
        if (me.role !== 'admin') {
          endSession(ADMIN_ONLY_MESSAGE)
          return
        }
        setUser(me)
        setVocab(vocabulary)
        setStatus('signedIn')
      } catch (failure) {
        if (cancelled) return
        if (failure instanceof NetworkError || getSessionToken() !== null) {
          // Sunucuya ulaşılamadı veya 401 dışı bir hata: oturumu koru, hatayı göster.
          setError(failure instanceof Error ? failure : new Error('Beklenmeyen bir hata oluştu.'))
          setStatus('error')
        }
        // 401 ise onUnauthorized zaten giriş ekranına döndürdü.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [api, attempt, endSession])

  const signIn = useCallback(
    async (username: string, password: string) => {
      const session = await api.login(username, password)
      // Yönetici olmayan hesabın token'ı saklanmaz; sunucu da zaten yönetim uçlarını reddeder.
      if (session.user.role !== 'admin') throw new Error(ADMIN_ONLY_MESSAGE)
      setSessionToken(session.access_token)
      try {
        const vocabulary = await api.vocabulary()
        storeToken(session.access_token)
        setVocab(vocabulary)
      } catch (failure) {
        setSessionToken(null)
        throw failure
      }
      setUser(session.user)
      setNotice(null)
      setError(null)
      setStatus('signedIn')
    },
    [api],
  )

  const signOut = useCallback(() => endSession(null), [endSession])
  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  const value = useMemo(
    () => ({ status, user, vocab, api, notice, error, signIn, signOut, retry }),
    [status, user, vocab, api, notice, error, signIn, signOut, retry],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
