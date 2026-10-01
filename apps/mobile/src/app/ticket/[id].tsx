import { Stack, useLocalSearchParams } from 'expo-router';
import { useCallback } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { ErrorState, LoadingState } from '@/components/states';
import { TicketActions } from '@/components/ticket-actions';
import { Badge, Banner, Card, Screen, Text } from '@/components/ui';
import { useSession } from '@/lib/auth';
import { describeEvent, eventNote } from '@/lib/events';
import { formatDateTime, ticketNumber } from '@/lib/format';
import { labelOf } from '@/lib/labels';
import type { TicketDetail } from '@/lib/types';
import { useResource } from '@/lib/use-resource';
import { spacing, useBadgeColors, useTheme } from '@/theme';

export default function TicketScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api } = useSession();
  const load = useCallback(() => api.getTicket(id), [api, id]);
  const { data: ticket, error, loading, retry, reload, refresh, refreshing } = useResource(load);

  return (
    <Screen edges={[]}>
      <Stack.Screen options={{ title: ticket ? ticketNumber(ticket.number) : 'Talep' }} />
      {loading && !ticket ? (
        <LoadingState message="Talep yükleniyor…" />
      ) : error && !ticket ? (
        <ErrorState error={error} onRetry={retry} />
      ) : ticket ? (
        <ScrollView
          contentContainerStyle={styles.container}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}>
          {error ? <Banner message={`Talep yenilenemedi: ${error.message}`} /> : null}
          <TicketBody ticket={ticket} />
          <TicketActions ticket={ticket} onChanged={reload} />
          <History ticket={ticket} />
        </ScrollView>
      ) : null}
    </Screen>
  );
}

function TicketBody({ ticket }: { ticket: TicketDetail }) {
  const { vocab, user } = useSession();
  const colors = useBadgeColors();
  const isOwner = ticket.created_by.id === user.id;

  return (
    <Card>
      <Text variant="title">{ticket.title}</Text>
      <View style={styles.badges}>
        <Badge label={labelOf(vocab.statuses, ticket.status)} color={colors.status[ticket.status]} />
        <Badge
          label={`Öncelik: ${labelOf(vocab.priorities, ticket.priority)}`}
          color={colors.priority[ticket.priority]}
        />
        {ticket.category ? (
          <Badge label={labelOf(vocab.categories, ticket.category)} color={colors.category} />
        ) : null}
      </View>

      {ticket.status === 'new' && isOwner ? (
        <Banner tone="info" message="Talebin alındı. İlgili ekibe yönlendirilmesi bekleniyor." />
      ) : null}
      {ticket.status === 'needs_review' ? (
        <Banner tone="info" message="Bu talep yönetici incelemesinde." />
      ) : null}

      <Text variant="body">{ticket.description}</Text>

      <Row label="Konum" value={ticket.location} />
      <Row label="Talep sahibi" value={ticket.created_by.display_name} />
      <Row label="Açılış" value={formatDateTime(ticket.created_at)} />
      <Row
        label="Ekip"
        value={ticket.team ? labelOf(vocab.teams, ticket.team.code) : 'Henüz yönlendirilmedi'}
      />
      {ticket.assignee ? <Row label="Görevli" value={ticket.assignee.display_name} /> : null}
      {ticket.missing_info.length > 0 ? (
        <Row
          label="Eksik bilgi"
          value={ticket.missing_info.map((code) => labelOf(vocab.missing_info, code)).join(', ')}
        />
      ) : null}
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text variant="label">{label}</Text>
      <Text variant="body">{value}</Text>
    </View>
  );
}

function History({ ticket }: { ticket: TicketDetail }) {
  const { vocab } = useSession();
  const theme = useTheme();
  // En yeni olay üstte.
  const events = [...ticket.events].reverse();

  return (
    <Card>
      <Text variant="heading">Geçmiş</Text>
      {events.map((event) => {
        const note = eventNote(event);
        return (
          <View key={event.id} style={[styles.event, { borderLeftColor: theme.border }]}>
            <Text variant="body">{describeEvent(event, vocab)}</Text>
            {note ? (
              <Text variant="muted" style={styles.note}>
                “{note}”
              </Text>
            ) : null}
            <Text variant="muted">{formatDateTime(event.created_at)}</Text>
          </View>
        );
      })}
    </Card>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.lg, gap: spacing.lg },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  row: { gap: 2 },
  event: { borderLeftWidth: 3, paddingLeft: spacing.md, gap: 2 },
  note: { fontStyle: 'italic' },
});
