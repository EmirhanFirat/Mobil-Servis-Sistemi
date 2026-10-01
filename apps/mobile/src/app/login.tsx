import { useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { Banner, Button, Field, Screen, Text } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { API_URL } from '@/lib/config';
import { spacing } from '@/theme';

export default function LoginScreen() {
  const { signIn, notice } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passwordRef = useRef<TextInput>(null);

  async function submit() {
    if (busy) return;
    if (!username.trim() || !password) {
      setError('Kullanıcı adı ve parolayı gir.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signIn(username.trim(), password);
      // Başarılı girişte yönlendirme kendiliğinden ana ekrana geçer.
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Giriş yapılamadı.');
      setBusy(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Text variant="title">TalepAkış</Text>
            <Text variant="muted">Bakım ve teknik servis talepleri</Text>
          </View>

          {notice ? <Banner message={notice} tone="info" /> : null}

          <Field
            label="Kullanıcı adı"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="username"
            textContentType="username"
            returnKeyType="next"
            onSubmitEditing={() => passwordRef.current?.focus()}
          />
          <Field
            ref={passwordRef}
            label="Parola"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoCapitalize="none"
            autoComplete="current-password"
            textContentType="password"
            returnKeyType="go"
            onSubmitEditing={submit}
          />

          {error ? <Banner message={error} /> : null}

          <Button title="Giriş yap" onPress={submit} loading={busy} />

          <Text variant="muted" style={styles.footer}>
            Sunucu: {API_URL}
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: spacing.xl, gap: spacing.lg, justifyContent: 'center', flexGrow: 1 },
  header: { gap: spacing.xs, marginBottom: spacing.md },
  footer: { textAlign: 'center', marginTop: spacing.md },
});
