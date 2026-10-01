import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { ApiError } from '@/lib/api';
import { useSession } from '@/lib/auth';
import { transitionAction } from '@/lib/actions';
import type { TicketDetail, TicketStatus } from '@/lib/types';
import { spacing } from '@/theme';

import { Banner, Button, Card, Field, Text } from './ui';

interface Props {
  ticket: TicketDetail;
  /** İşlem başarılı olunca veya durum değişmiş çıkınca ayrıntıyı yenilemek için. */
  onChanged: () => Promise<void> | void;
}

/**
 * Sunucunun bu kullanıcı için izin verdiği geçişleri (allowed_transitions) düğme olarak gösterir.
 * İstemci izin kararı vermez; yalnızca sunucunun söylediğini sunar. Onay adımı satır içidir
 * (Alert.alert web'de çalışmadığı için).
 */
export function TicketActions({ ticket, onChanged }: Props) {
  const { api } = useSession();
  const [pending, setPending] = useState<TicketStatus | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (ticket.allowed_transitions.length === 0) return null;

  const chosen = pending ? transitionAction(ticket.status, pending) : null;

  function cancel() {
    setPending(null);
    setNote('');
    setError(null);
  }

  async function confirm() {
    if (!pending || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.transition(ticket.id, pending, note.trim() || undefined);
      setPending(null);
      setNote('');
      await onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'İşlem yapılamadı.');
      // Durum başka biri tarafından değişmiş olabilir: güncel hâli ve izinleri çek.
      if (failure instanceof ApiError && (failure.status === 409 || failure.status === 403)) {
        setPending(null);
        await onChanged();
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <Text variant="heading">İşlemler</Text>

      {chosen ? (
        <View style={styles.stack}>
          <Text variant="body">{chosen.label}</Text>
          {chosen.hint ? <Text variant="muted">{chosen.hint}</Text> : null}
          <Field
            label="Not (isteğe bağlı)"
            value={note}
            onChangeText={setNote}
            maxLength={500}
            multiline
            placeholder="Kısa bir açıklama ekleyebilirsin"
          />
          {error ? <Banner message={error} /> : null}
          <Button
            title="Onayla"
            variant={chosen.destructive ? 'danger' : 'primary'}
            onPress={confirm}
            loading={busy}
          />
          <Button title="Vazgeç" variant="secondary" onPress={cancel} disabled={busy} />
        </View>
      ) : (
        <View style={styles.stack}>
          {error ? <Banner message={error} /> : null}
          {ticket.allowed_transitions.map((to, index) => {
            const action = transitionAction(ticket.status, to);
            return (
              <Button
                key={to}
                title={action.label}
                variant={action.destructive ? 'danger' : index === 0 ? 'primary' : 'secondary'}
                onPress={() => {
                  setError(null);
                  setPending(to);
                }}
              />
            );
          })}
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.sm },
});
