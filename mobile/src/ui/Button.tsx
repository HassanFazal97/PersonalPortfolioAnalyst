import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { color, radius, space, MIN_TAP } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type ButtonProps = {
  label: string;
  onPress?: () => void;
  variant?: 'primary' | 'ghost' | 'danger' | 'link';
  size?: 'md' | 'sm';
  loading?: boolean;
  disabled?: boolean;
  /** Full-width by default; set false for a button that sits inline. */
  block?: boolean;
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  size = 'md',
  loading,
  disabled,
  block = true,
}: ButtonProps) {
  const inert = disabled || loading;

  if (variant === 'link') {
    return (
      <Pressable
        onPress={onPress}
        disabled={inert}
        accessibilityRole="button"
        accessibilityState={{ disabled: !!inert, busy: !!loading }}
        style={styles.link}
      >
        <Txt variant="bodySm" tone={inert ? 'ink3' : 'accent'} style={styles.linkLabel}>
          {label}
        </Txt>
      </Pressable>
    );
  }

  return (
    <Pressable
      onPress={onPress}
      disabled={inert}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!inert, busy: !!loading }}
      style={({ pressed }) => [
        styles.base,
        size === 'sm' && styles.sm,
        block && styles.block,
        variant === 'primary' && styles.primary,
        variant === 'ghost' && styles.ghost,
        variant === 'danger' && styles.danger,
        pressed && !inert && styles.pressed,
        inert && styles.inert,
      ]}
    >
      <View style={styles.inner}>
        {loading ? (
          <ActivityIndicator
            size="small"
            color={variant === 'ghost' ? color.accentText : color.white}
          />
        ) : null}
        <Txt
          variant="body"
          tone={variant === 'ghost' ? 'ink' : 'inverse'}
          style={styles.label}
        >
          {label}
        </Txt>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: MIN_TAP,
    borderRadius: radius.m,
    paddingHorizontal: space.s4,
    paddingVertical: space.s3,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sm: { minHeight: 36, paddingVertical: space.s2, borderRadius: radius.s },
  block: { alignSelf: 'stretch' },
  primary: { backgroundColor: color.accent },
  ghost: {
    backgroundColor: color.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.lineStrong,
  },
  danger: { backgroundColor: color.loss },
  pressed: { opacity: 0.86 },
  inert: { opacity: 0.5 },
  inner: { flexDirection: 'row', alignItems: 'center', gap: space.s2 },
  label: { fontWeight: '700' },
  link: { minHeight: 32, justifyContent: 'center' },
  linkLabel: { fontWeight: '600' },
});
