import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const TOKEN_KEY = 'talepakis.token';

/**
 * Oturum belirteci cihazın güvenli deposunda (iOS Keychain / Android Keystore) saklanır.
 * Web'de güvenli depo yoktur; yalnızca geliştirme önizlemesi için localStorage kullanılır.
 * Depo okunamazsa uygulama çökmez, kullanıcı yeniden giriş yapar.
 */
export async function loadToken(): Promise<string | null> {
  try {
    if (Platform.OS === 'web') return globalThis.localStorage?.getItem(TOKEN_KEY) ?? null;
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function saveToken(token: string): Promise<void> {
  try {
    if (Platform.OS === 'web') globalThis.localStorage?.setItem(TOKEN_KEY, token);
    else await SecureStore.setItemAsync(TOKEN_KEY, token);
  } catch {
    // Saklanamadı: oturum bu açılışta çalışır, sonraki açılışta yeniden giriş istenir.
  }
}

export async function clearToken(): Promise<void> {
  try {
    if (Platform.OS === 'web') globalThis.localStorage?.removeItem(TOKEN_KEY);
    else await SecureStore.deleteItemAsync(TOKEN_KEY);
  } catch {
    // Silinemediyse bir sonraki açılışta /auth/me reddedecek ve token temizlenecek.
  }
}
