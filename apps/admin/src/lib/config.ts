/**
 * API adresi: VITE_API_URL (derleme zamanında pakete gömülür, gizli bilgi koyma) veya
 * geliştirme varsayılanı. Üretimde https:// adres verilmelidir.
 */
export function resolveApiUrl(explicit?: string): string {
  if (explicit) return explicit.replace(/\/+$/, '')
  return 'http://127.0.0.1:8000'
}

export const API_URL = resolveApiUrl(import.meta.env.VITE_API_URL)
