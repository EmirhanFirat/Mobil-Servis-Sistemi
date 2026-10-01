import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { ErrorState, LoadingState } from '@/components/states';
import { Screen } from '@/components/ui';
import { AuthProvider, useAuth } from '@/lib/auth';
import { useTheme } from '@/theme';

export default function RootLayout() {
  return (
    <AuthProvider>
      <RootNavigator />
    </AuthProvider>
  );
}

function RootNavigator() {
  const { status, error, retry } = useAuth();
  const theme = useTheme();

  // Gezinme çubukları (başlık, sekmeler) uygulamanın paletini kullansın.
  const base = theme.scheme === 'dark' ? DarkTheme : DefaultTheme;
  const navigationTheme = {
    ...base,
    colors: {
      ...base.colors,
      primary: theme.primary,
      background: theme.background,
      card: theme.card,
      text: theme.text,
      border: theme.border,
    },
  };

  if (status === 'loading') {
    return (
      <Screen>
        <LoadingState message="Oturum kontrol ediliyor…" />
      </Screen>
    );
  }
  if (status === 'error') {
    return (
      <Screen>
        <ErrorState error={error ?? new Error('Sunucuya ulaşılamadı.')} onRetry={retry} />
      </Screen>
    );
  }

  const signedIn = status === 'signedIn';
  return (
    <ThemeProvider value={navigationTheme}>
      <StatusBar style="auto" />
      <Stack screenOptions={{ headerShown: false }}>
        {/* Yönlendirme istemci tarafıdır ve yalnızca kullanım kolaylığı içindir; erişimi
            asıl sunucu denetler (her istekte token ve rol doğrulanır). */}
        <Stack.Protected guard={!signedIn}>
          <Stack.Screen name="login" />
        </Stack.Protected>
        <Stack.Protected guard={signedIn}>
          <Stack.Screen name="(app)" />
          <Stack.Screen
            name="ticket/[id]"
            options={{ headerShown: true, title: 'Talep', headerBackTitle: 'Geri' }}
          />
        </Stack.Protected>
      </Stack>
    </ThemeProvider>
  );
}
