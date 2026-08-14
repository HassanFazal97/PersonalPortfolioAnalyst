import { Pressable, StyleSheet, View } from 'react-native';

import { color, radius, space, HIT_SLOP } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type BannerTone = 'warn' | 'setup';

export type BannerProps = {
  /** Leading clause, rendered bold — the web's `<strong>` opener. */
  title: string;
  body: string;
  tone?: BannerTone;
  actionLabel?: string;
  onAction?: () => void;
  /** Omit to make the banner non-dismissible, as the trial banner is. */
  onDismiss?: () => void;
  dismissLabel?: string;
};

/**
 * `.warn-banner`. Two tones: `warn` for something broken (amber) and `setup`
 * for a nudge (lavender wash).
 */
export function Banner({
  title,
  body,
  tone = 'warn',
  actionLabel,
  onAction,
  onDismiss,
  dismissLabel = 'Dismiss',
}: BannerProps) {
  const setup = tone === 'setup';
  return (
    <View style={[styles.root, setup ? styles.setup : styles.warn]}>
      <Txt variant="bodySm" tone={setup ? 'ink2' : 'warn'}>
        <Txt variant="bodySm" tone={setup ? 'ink' : 'warn'} style={styles.strong}>
          {title}
        </Txt>{' '}
        {body}
      </Txt>
      {actionLabel || onDismiss ? (
        <View style={styles.actions}>
          {actionLabel && onAction ? (
            <Pressable
              onPress={onAction}
              hitSlop={HIT_SLOP}
              accessibilityRole="button"
              style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
            >
              <Txt variant="bodySm" tone="inverse" style={styles.btnLabel}>
                {actionLabel}
              </Txt>
            </Pressable>
          ) : null}
          {onDismiss ? (
            <Pressable onPress={onDismiss} hitSlop={HIT_SLOP} accessibilityRole="button">
              <Txt variant="bodySm" tone="ink3">
                {dismissLabel}
              </Txt>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    borderRadius: radius.m,
    borderWidth: StyleSheet.hairlineWidth,
    padding: space.s3,
    marginBottom: space.s3,
    gap: space.s2,
  },
  warn: { backgroundColor: color.warnBg, borderColor: color.warnBorder },
  setup: { backgroundColor: color.accentWash, borderColor: color.accentBorder },
  strong: { fontWeight: '700' },
  actions: { flexDirection: 'row', alignItems: 'center', gap: space.s4 },
  btn: {
    backgroundColor: color.accent,
    borderRadius: radius.s,
    paddingHorizontal: space.s3,
    paddingVertical: space.s2,
  },
  btnPressed: { backgroundColor: color.accentPressed },
  btnLabel: { fontWeight: '700' },
});
