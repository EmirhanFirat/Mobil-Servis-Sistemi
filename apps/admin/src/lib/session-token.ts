/**
 * Bellekteki oturum belirteci. API istemcisi her istekte buradan okur. Kalıcı kopya
 * sessionStorage'dadır: sekme/pencere kapanınca silinir (localStorage'dan daha kısa ömürlü).
 */
const STORAGE_KEY = 'talepakis.admin.token'

let current: string | null = null

export function getSessionToken(): string | null {
  return current
}

export function setSessionToken(token: string | null): void {
  current = token
}

export function readStoredToken(): string | null {
  try {
    return globalThis.sessionStorage?.getItem(STORAGE_KEY) ?? null
  } catch {
    return null
  }
}

export function storeToken(token: string | null): void {
  try {
    if (token) globalThis.sessionStorage?.setItem(STORAGE_KEY, token)
    else globalThis.sessionStorage?.removeItem(STORAGE_KEY)
  } catch {
    // Depo kullanılamıyorsa oturum yalnızca bu sayfa açıkken geçerli kalır.
  }
}
