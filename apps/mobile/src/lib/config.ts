import Constants from 'expo-constants';
import { Platform } from 'react-native';

const API_PORT = 8000;

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

interface Inputs {
  /** EXPO_PUBLIC_API_URL: açıkça verilen adres (gizli bilgi içermez; pakete gömülür). */
  explicitUrl?: string;
  /** Expo geliştirme sunucusunun adresi, ör. "192.168.1.20:8081". */
  hostUri?: string | null;
  os: string;
}

/**
 * API adresini çözer. Öncelik: açık adres → geliştirme sunucusunun bilgisayar adresi
 * (telefonda Expo Go ile) → platform varsayılanı (Android emülatörü 10.0.2.2, diğerleri 127.0.0.1).
 * Telefonda "localhost" telefonun kendisidir; bu yüzden bilgisayarın ağ adresi kullanılır.
 */
export function resolveApiUrl({ explicitUrl, hostUri, os }: Inputs): string {
  if (explicitUrl) return explicitUrl.replace(/\/+$/, '');
  const host = hostUri?.split(':')[0];
  if (host && !LOOPBACK_HOSTS.has(host)) return `http://${host}:${API_PORT}`;
  if (os === 'android') return `http://10.0.2.2:${API_PORT}`;
  return `http://127.0.0.1:${API_PORT}`;
}

export const API_URL = resolveApiUrl({
  explicitUrl: process.env.EXPO_PUBLIC_API_URL,
  hostUri: Constants.expoConfig?.hostUri,
  os: Platform.OS,
});
