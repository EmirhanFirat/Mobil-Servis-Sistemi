import { Pressable, StyleSheet, View } from 'react-native';

import { formatDateTime, ticketNumber } from '@/lib/format';
import { labelOf } from '@/lib/labels';
import type { TicketSummary, Vocabulary } from '@/lib/types';
import { spacing, useBadgeColors, useTheme } from '@/theme';

import { Badge, Text } from './ui';

interface Props {
  ticket: TicketSummary;
  vocab: Vocabulary;
  onPress: () => void;
  /** Teknik görevli listesinde talep sahibini de göster. */
  showOwner?: boolean;
}

export function TicketCard({ ticket, vocab, onPress, showOwner }: Props) {
  const theme = useTheme();
  const colors = useBadgeColors();
  const statusLabel = labelOf(vocab.statuses, ticket.status);
  const priorityLabel = labelOf(vocab.priorities, ticket.priority);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${ticketNumber(ticket.number)} ${ticket.title}, ${statusLabel}`}
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: theme.card, borderColor: theme.border, opacity: pressed ? 0.85 : 1 },
      ]}>
      <View style={styles.row}>
        <Text variant="label">{ticketNumber(ticket.number)}</Text>
        <Text variant="muted">{formatDateTime(ticket.created_at)}</Text>
      </View>
      <Text variant="heading">{ticket.title}</Text>
      <Text variant="muted">{ticket.location}</Text>
      <View style={styles.badges}>
        <Badge label={statusLabel} color={colors.status[ticket.status]} />
        {ticket.priority !== 'normal' ? (
          <Badge label={`Öncelik: ${priorityLabel}`} color={colors.priority[ticket.priority]} />
        ) : null}
        {ticket.team ? (
          <Badge label={labelOf(vocab.teams, ticket.team.code)} color={colors.neutral} />
        ) : null}
      </View>
      {showOwner ? <Text variant="muted">Talep sahibi: {ticket.created_by.display_name}</Text> : null}
      {ticket.assignee ? <Text variant="muted">Görevli: {ticket.assignee.display_name}</Text> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: 12, padding: spacing.lg, gap: spacing.xs },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xs },
});
