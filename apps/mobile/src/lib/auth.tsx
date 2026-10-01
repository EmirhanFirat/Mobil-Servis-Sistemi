import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { NetworkError, createApiClient, type ApiClient } from './api';
import { API_URL } from './config';
import { getSessionToken, setSessionToken } from './session-token';
import { clearToken, loadToken, saveToken } from './storage';
import type { User, Vocabulary } from './types';

export type AuthStatus = 'loading' | 'signedOut' | 'signedIn' | 'error';

interface AuthValue {
  status: AuthStatus;
  user: User | null;
  /** Oturum açıkken her zaman dolu: Türkçe görünen adlar sunucudan gelir. */
  vocab: Vocabulary | null;
  api: ApiClient;
  /** Giriş ekranında gösterilecek bilgi (ör. oturum süresi doldu). */
  notice: string | null;
  /** Açılışta sunucuya ulaşılamadığında gösterilecek hata (türü korunur: NetworkError/ApiError). */
  error: Error | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<User | null>(null);
  const [vocab, setVocab] = useState<Vocabulary | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  const expireSession = useCallback(() => {
    setSessionToken(null);
    void clearToken();
    setUser(null);
    setVocab(null);
    setNotice('Oturumun süresi doldu. Lütfen yeniden giriş yap.');
    setStatus('signedOut');
  }, []);

  const api = useMemo(
    () =>
      createApiClient({
        baseUrl: API_URL,
        getToken: getSessionToken,
        onUnauthorized: expireSession,
      }),
    [expireSession],
  );

  // Açılışta kayıtlı oturumu doğrula. Sunucuya ulaşılamıyorsa çıkış yapmak yerine hata göster.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setStatus('loading');
      const token = await loadToken();
      if (cancelled) return;
      if (!token) {
        setStatus('signedOut');
        return;
      }
      setSessionToken(token);
      try {
        const [me, vocabulary] = await Promise.all([api.me(), api.vocabulary()]);
        if (cancelled) return;
        setUser(me);
        setVocab(vocabulary);
        setStatus('signedIn');
      } catch (failure) {
        if (cancelled) return;
        if (failure instanceof NetworkError || getSessionToken() !== null) {
          // Sunucuya ulaşılamadı veya 401 dışı bir hata: oturumu koru, hatayı göster.
          setError(failure instanceof Error ? failure : new Error('Beklenmeyen bir hata oluştu.'));
          setStatus('error');
        }
        // 401 ise onUnauthorized zaten giriş ekranına döndürdü.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, attempt]);

  const signIn = useCallback(
    async (username: string, password: string) => {
      const session = await api.login(username, password);
      setSessionToken(session.access_token);
      try {
        const vocabulary = await api.vocabulary();
        await saveToken(session.access_token);
        setVocab(vocabulary);
      } catch (failure) {
        setSessionToken(null);
        throw failure;
      }
      setUser(session.user);
      setNotice(null);
      setError(null);
      setStatus('signedIn');
    },
    [api],
  );

  const signOut = useCallback(async () => {
    setSessionToken(null);
    await clearToken();
    setUser(null);
    setVocab(null);
    setNotice(null);
    setStatus('signedOut');
  }, []);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const value = useMemo(
    () => ({ status, user, vocab, api, notice, error, signIn, signOut, retry }),
    [status, user, vocab, api, notice, error, signIn, signOut, retry],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth, AuthProvider içinde kullanılmalı.');
  return value;
}

/** Oturum açık ekranlarda kullanılır; kullanıcı ve sözlük kesinlikle doludur. */
export function useSession(): AuthValue & { user: User; vocab: Vocabulary } {
  const value = useAuth();
  if (!value.user || !value.vocab) throw new Error('Oturum açık değil.');
  return value as AuthValue & { user: User; vocab: Vocabulary };
}
