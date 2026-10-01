import { Tabs } from 'expo-router';

import { useSession } from '@/lib/auth';
import { useTheme } from '@/theme';

export default function AppLayout() {
  const { user } = useSession();
  const theme = useTheme();
  // İş listesi yalnızca teknik görevli ve yönetici içindir. Bu yalnızca gösterimdir;
  // yetkiyi sunucu verir (talep sahibi kuyruk isteğinde boş liste alır).
  const canWork = user.role !== 'requester';

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: theme.primary,
        tabBarInactiveTintColor: theme.muted,
        tabBarStyle: { backgroundColor: theme.card, borderTopColor: theme.border },
        tabBarLabelStyle: { fontSize: 14, fontWeight: '600' },
        tabBarIcon: () => null,
        tabBarIconStyle: { display: 'none' },
      }}>
      <Tabs.Screen name="index" options={{ title: 'Taleplerim' }} />
      <Tabs.Screen name="new" options={{ title: 'Yeni talep' }} />
      <Tabs.Screen name="queue" options={{ title: 'İş listesi', href: canWork ? undefined : null }} />
      <Tabs.Screen name="account" options={{ title: 'Hesap' }} />
    </Tabs>
  );
}
