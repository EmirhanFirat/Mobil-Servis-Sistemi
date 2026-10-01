import { StyleSheet, View } from 'react-native';

import { Button, Card, Screen, Text } from '@/components/ui';
import { useSession } from '@/lib/auth';
import { API_URL } from '@/lib/config';
import { labelOf } from '@/lib/labels';
import { spacing } from '@/theme';

export default function AccountScreen() {
  const { user, vocab, signOut } = useSession();

  return (
    <Screen>
      <View style={styles.container}>
        <Text variant="title">Hesap</Text>
        <Card>
          <Text variant="heading">{user.display_name}</Text>
          <Text variant="muted">Kullanıcı adı: {user.username}</Text>
          <Text variant="muted">Rol: {labelOf(vocab.roles, user.role)}</Text>
          {user.teams.length > 0 ? (
            <Text variant="muted">
              Ekip: {user.teams.map((team) => labelOf(vocab.teams, team.code)).join(', ')}
            </Text>
          ) : null}
        </Card>
        <Text variant="muted">Sunucu: {API_URL}</Text>
        <Button title="Çıkış yap" variant="secondary" onPress={() => void signOut()} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.lg, gap: spacing.lg },
});
