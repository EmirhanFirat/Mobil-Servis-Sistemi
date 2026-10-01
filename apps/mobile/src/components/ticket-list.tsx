import { useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';

import { useSession } from '@/lib/auth';
import type { TicketStatus } from '@/lib/types';
import { useResource } from '@/lib/use-resource';
import { spacing, useTheme } from '@/theme';

import { EmptyState, ErrorState, LoadingState } from './states';
import { TicketCard } from './ticket-card';
import { Banner, Screen, Text } from './ui';

export interface StatusFilter {
  label: string;
  /** Boş/undefined: süzgeç yok (tümü). */
  statuses?: TicketStatus[];
}

interface Props {
  title: string;
  scope: 'mine' | 'queue';
  filters?: StatusFilter[];
  emptyTitle: string;
  emptyMessage: string;
  emptyActionLabel?: string;
  onEmptyAction?: () => void;
  showOwner?: boolean;
}

export function TicketListScreen({
  title,
  scope,
  filters,
  emptyTitle,
  emptyMessage,
  emptyActionLabel,
  onEmptyAction,
  showOwner,
}: Props) {
  const { api, vocab } = useSession();
  const router = useRouter();
  const theme = useTheme();
  const [filterIndex, setFilterIndex] = useState(0);
  const statuses = filters?.[filterIndex]?.statuses;

  const load = useCallback(
    () => api.listTickets({ scope, status: statuses, limit: 100 }),
    [api, scope, statuses],
  );
  const { data, error, loading, retry, refresh, refreshing } = useResource(load);

  return (
    <Screen>
      <View style={styles.header}>
        <Text variant="title">{title}</Text>
        {filters && filters.length > 1 ? (
          <View style={styles.chips} accessibilityRole="tablist">
            {filters.map((filter, index) => {
              const active = index === filterIndex;
              return (
                <Pressable
                  key={filter.label}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: active }}
                  onPress={() => setFilterIndex(index)}
                  style={[
                    styles.chip,
                    {
                      backgroundColor: active ? theme.primary : theme.card,
                      borderColor: active ? theme.primary : theme.border,
                    },
                  ]}>
                  <Text
                    variant="muted"
                    style={{ color: active ? theme.onPrimary : theme.text, fontWeight: '600' }}>
                    {filter.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        ) : null}
      </View>

      {loading && !data ? (
        <LoadingState message="Talepler yükleniyor…" />
      ) : error && !data ? (
        <ErrorState error={error} onRetry={retry} />
      ) : data ? (
        <FlatList
          data={data.items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={[styles.list, data.items.length === 0 && styles.listEmpty]}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
          ListHeaderComponent={
            error ? <Banner message={`Liste yenilenemedi: ${error.message}`} /> : null
          }
          ListEmptyComponent={
            <EmptyState
              title={emptyTitle}
              message={emptyMessage}
              actionLabel={emptyActionLabel}
              onAction={onEmptyAction}
            />
          }
          ItemSeparatorComponent={() => <View style={{ height: spacing.md }} />}
          renderItem={({ item }) => (
            <TicketCard
              ticket={item}
              vocab={vocab}
              showOwner={showOwner}
              onPress={() => router.push(`/ticket/${item.id}`)}
            />
          )}
        />
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingTop: spacing.lg, gap: spacing.md },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 6 },
  list: { padding: spacing.lg },
  listEmpty: { flexGrow: 1 },
});
