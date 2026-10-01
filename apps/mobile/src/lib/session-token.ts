/**
 * Bellekteki oturum belirteci. API istemcisi her istekte buradan okur; kalıcı kopya
 * `storage.ts` ile cihazın güvenli deposundadır. React durumu değildir (ekranı yeniden çizmez).
 */
let current: string | null = null;

export function getSessionToken(): string | null {
  return current;
}

export function setSessionToken(token: string | null): void {
  current = token;
}
