import { useRouter } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet } from 'react-native';

import { Banner, Button, Field, Screen, Text } from '@/components/ui';
import { useSession } from '@/lib/auth';
import { TICKET_LIMITS as LIMITS, validateTicket, type TicketField } from '@/lib/validation';
import { spacing } from '@/theme';

export default function NewTicketScreen() {
  const { api } = useSession();
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errors = validateTicket({ title, description, location });
  const show = (field: TicketField) => (submitted ? (errors[field] ?? null) : null);

  async function submit() {
    if (busy) return;
    setSubmitted(true);
    if (Object.keys(errors).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createTicket({
        title: title.trim(),
        description: description.trim(),
        location: location.trim(),
      });
      setTitle('');
      setDescription('');
      setLocation('');
      setSubmitted(false);
      // Önce listeye dön, sonra ayrıntıyı aç: geri tuşu listeye götürür.
      router.navigate('/');
      router.push(`/ticket/${created.id}`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Talep gönderilemedi.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <Text variant="title">Yeni talep</Text>

          <Banner
            tone="info"
            message="Bu uygulama acil yardım sistemi değildir. Yangın, elektrik çarpması, gaz kaçağı gibi can güvenliği riski varsa önce 112'yi veya kampüs güvenliğini ara."
          />

          <Field
            label="Başlık"
            value={title}
            onChangeText={setTitle}
            maxLength={LIMITS.title}
            placeholder="Kısaca sorun nedir?"
            error={show('title')}
          />
          <Field
            label="Açıklama"
            value={description}
            onChangeText={setDescription}
            maxLength={LIMITS.description}
            multiline
            numberOfLines={5}
            textAlignVertical="top"
            style={styles.multiline}
            placeholder="Ne oldu, ne zamandır var, durum acil mi?"
            error={show('description')}
          />
          <Field
            label="Bina / konum"
            value={location}
            onChangeText={setLocation}
            maxLength={LIMITS.location}
            placeholder="Ör. B Blok, 2. kat koridor"
            error={show('location')}
          />

          {error ? <Banner message={error} /> : null}

          <Button title="Talebi gönder" onPress={submit} loading={busy} />
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: spacing.lg, gap: spacing.lg },
  multiline: { minHeight: 120 },
});
