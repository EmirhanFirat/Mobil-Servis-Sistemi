import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { ApiError, NetworkError } from '@/lib/api';
import { API_URL } from '@/lib/config';
import { spacing, useTheme } from '@/theme';

import { Button, Text } from './ui';

export function LoadingState({ message = 'Yükleniyor…' }: { message?: string }) {
  const theme = useTheme();
  return (
    <View style={styles.center} accessibilityRole="progressbar" accessibilityLabel={message}>
      <ActivityIndicator size="large" color={theme.primary} />
      <Text variant="muted">{message}</Text>
    </View>
  );
}

interface EmptyProps {
  title: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ title, message, actionLabel, onAction }: EmptyProps) {
  return (
    <View style={styles.center}>
      <Text variant="heading">{title}</Text>
      {message ? (
        <Text variant="muted" style={styles.centerText}>
          {message}
        </Text>
      ) : null}
      {actionLabel && onAction ? (
        <View style={styles.action}>
          <Button title={actionLabel} onPress={onAction} />
        </View>
      ) : null}
    </View>
  );
}

function describe(error: Error): { title: string; message: string; showServer: boolean } {
  if (error instanceof NetworkError) {
    return { title: 'Bağlantı sorunu', message: error.message, showServer: true };
  }
  if (error instanceof ApiError) {
    if (error.status === 404) return { title: 'Bulunamadı', message: error.message, showServer: false };
    if (error.status === 403) return { title: 'Erişim yok', message: error.message, showServer: false };
  }
  return { title: 'Bir sorun oluştu', message: error.message, showServer: false };
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const { title, message, showServer } = describe(error);
  return (
    <View style={styles.center} accessibilityRole="alert">
      <Text variant="heading">{title}</Text>
      <Text variant="muted" style={styles.centerText}>
        {message}
      </Text>
      {showServer ? <Text variant="muted">Sunucu: {API_URL}</Text> : null}
      {onRetry ? (
        <View style={styles.action}>
          <Button title="Tekrar dene" onPress={onRetry} variant="secondary" />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    padding: spacing.xl,
  },
  centerText: { textAlign: 'center' },
  action: { marginTop: spacing.md, alignSelf: 'stretch', maxWidth: 280 },
});
