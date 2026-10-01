import type { ReactNode, Ref } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text as RNText,
  TextInput,
  View,
  type TextInputProps,
  type TextProps,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { spacing, useTheme } from '@/theme';

type Variant = 'title' | 'heading' | 'body' | 'muted' | 'label';

interface Props extends TextProps {
  variant?: Variant;
}

export function Text({ variant = 'body', style, ...rest }: Props) {
  const theme = useTheme();
  const color = variant === 'muted' || variant === 'label' ? theme.muted : theme.text;
  return <RNText {...rest} style={[textStyles[variant], { color }, style]} />;
}

const textStyles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700' },
  heading: { fontSize: 17, fontWeight: '600' },
  body: { fontSize: 15, lineHeight: 21 },
  muted: { fontSize: 13, lineHeight: 18 },
  label: { fontSize: 12, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.4 },
});

export function Screen({ children, edges }: { children: ReactNode; edges?: ('top' | 'bottom')[] }) {
  const theme = useTheme();
  return (
    <SafeAreaView
      edges={edges ?? ['top']}
      style={[styles.screen, { backgroundColor: theme.background }]}>
      {children}
    </SafeAreaView>
  );
}

export function Card({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.border }]}>
      {children}
    </View>
  );
}

interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  loading?: boolean;
  disabled?: boolean;
}

export function Button({ title, onPress, variant = 'primary', loading, disabled }: ButtonProps) {
  const theme = useTheme();
  const inactive = disabled || loading;
  const background =
    variant === 'primary' ? theme.primary : variant === 'danger' ? theme.dangerSoft : 'transparent';
  const color =
    variant === 'primary' ? theme.onPrimary : variant === 'danger' ? theme.danger : theme.primary;
  const borderColor = variant === 'secondary' ? theme.border : background;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: background, borderColor, opacity: inactive ? 0.55 : pressed ? 0.85 : 1 },
      ]}>
      {loading ? (
        <ActivityIndicator color={color} />
      ) : (
        <RNText style={[styles.buttonText, { color }]}>{title}</RNText>
      )}
    </Pressable>
  );
}

interface FieldProps extends TextInputProps {
  label: string;
  error?: string | null;
  ref?: Ref<TextInput>;
}

export function Field({ label, error, style, ref, ...rest }: FieldProps) {
  const theme = useTheme();
  return (
    <View style={styles.field}>
      <Text variant="label">{label}</Text>
      <TextInput
        ref={ref}
        accessibilityLabel={label}
        placeholderTextColor={theme.muted}
        {...rest}
        style={[
          styles.input,
          {
            color: theme.text,
            backgroundColor: theme.inputBackground,
            borderColor: error ? theme.danger : theme.border,
          },
          style,
        ]}
      />
      {error ? (
        <Text variant="muted" style={{ color: theme.danger }} accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

export function Badge({ label, color }: { label: string; color: string }) {
  return (
    <View style={[styles.badge, { backgroundColor: `${color}1F` }]}>
      <RNText style={[styles.badgeText, { color }]}>{label}</RNText>
    </View>
  );
}

export function Banner({ message, tone = 'danger' }: { message: string; tone?: 'danger' | 'info' }) {
  const theme = useTheme();
  return (
    <View
      accessibilityRole="alert"
      style={[
        styles.banner,
        { backgroundColor: tone === 'danger' ? theme.dangerSoft : theme.card, borderColor: theme.border },
      ]}>
      <Text variant="muted" style={{ color: tone === 'danger' ? theme.danger : theme.muted }}>
        {message}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  card: { borderWidth: 1, borderRadius: 12, padding: spacing.lg, gap: spacing.sm },
  button: {
    minHeight: 46,
    borderRadius: 10,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  buttonText: { fontSize: 15, fontWeight: '600' },
  field: { gap: spacing.xs },
  input: {
    minHeight: 46,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 15,
  },
  badge: { alignSelf: 'flex-start', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 },
  badgeText: { fontSize: 12, fontWeight: '600' },
  banner: { borderWidth: 1, borderRadius: 10, padding: spacing.md },
});
