import { useRouter } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { color, radius, space, HIT_SLOP } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export const TOTAL_STEPS = 7;

export type StepProps = {
  step: number;
  title: string;
  blurb?: string;
  children: ReactNode;
  /** Pinned to the bottom, outside the scroll area. */
  footer?: ReactNode;
  onBack?: () => void;
  onSkip?: () => void;
  skipLabel?: string;
};

/**
 * Shared frame for the wizard: progress bar, title block, and the footer that
 * holds the primary action. Every step gets a way out — a user trapped in
 * onboarding is a user who never sees the product.
 */
export function Step({
  step,
  title,
  blurb,
  children,
  footer,
  onBack,
  onSkip,
  skipLabel = 'Skip',
}: StepProps) {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.nav}>
        <Pressable
          onPress={onBack ?? (() => router.back())}
          hitSlop={HIT_SLOP}
          accessibilityRole="button"
          style={styles.navSide}
        >
          <Txt variant="body" tone="accent">
            {step > 1 ? '‹ Back' : ''}
          </Txt>
        </Pressable>
        <Txt variant="caption" tone="ink3">
          Step {step} of {TOTAL_STEPS}
        </Txt>
        <Pressable
          onPress={onSkip}
          hitSlop={HIT_SLOP}
          accessibilityRole="button"
          style={[styles.navSide, styles.navRight]}
        >
          <Txt variant="body" tone="ink3">
            {onSkip ? skipLabel : ''}
          </Txt>
        </Pressable>
      </View>

      <View
        style={styles.progress}
        accessibilityRole="progressbar"
        accessibilityValue={{ min: 0, max: TOTAL_STEPS, now: step }}
      >
        {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
          <View key={i} style={[styles.tick, i < step && styles.tickOn]} />
        ))}
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Txt variant="title" tone="ink">
          {title}
        </Txt>
        {blurb ? (
          <Txt variant="bodySm" tone="ink3" style={styles.blurb}>
            {blurb}
          </Txt>
        ) : null}
        {children}
      </ScrollView>

      {footer ? (
        <View style={[styles.footer, { paddingBottom: insets.bottom + space.s3 }]}>{footer}</View>
      ) : null}
    </View>
  );
}

/** A tappable answer card — the wizard's only input idiom. */
export function Choice({
  label,
  hint,
  selected,
  onPress,
  multi,
}: {
  label: string;
  hint?: string;
  selected: boolean;
  onPress: () => void;
  multi?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole={multi ? 'checkbox' : 'radio'}
      accessibilityState={{ selected, checked: selected }}
      style={[styles.choice, selected && styles.choiceOn]}
    >
      <View style={styles.choiceText}>
        <Txt variant="bodySm" tone="ink" style={styles.choiceLabel}>
          {label}
        </Txt>
        {hint ? (
          <Txt variant="caption" tone="ink3">
            {hint}
          </Txt>
        ) : null}
      </View>
      <View
        style={[
          multi ? styles.box : styles.radio,
          selected && (multi ? styles.boxOn : styles.radioOn),
        ]}
      >
        {multi && selected ? (
          <Txt variant="caption" tone="inverse">
            ✓
          </Txt>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.s4,
    paddingVertical: space.s2,
  },
  navSide: { minWidth: 64 },
  navRight: { alignItems: 'flex-end' },
  progress: { flexDirection: 'row', gap: 4, paddingHorizontal: space.s4, paddingBottom: space.s4 },
  tick: { flex: 1, height: 3, borderRadius: 2, backgroundColor: color.surface3 },
  tickOn: { backgroundColor: color.accent },
  content: { paddingHorizontal: space.s4, paddingBottom: space.s7 },
  blurb: { marginTop: space.s2, marginBottom: space.s4 },
  footer: {
    paddingHorizontal: space.s4,
    paddingTop: space.s3,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.line,
    backgroundColor: color.surface1,
    gap: space.s2,
  },
  choice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.s3,
    borderWidth: 1.5,
    borderColor: color.lineStrong,
    borderRadius: radius.l,
    padding: space.s3,
    marginBottom: space.s2,
    backgroundColor: color.surface1,
  },
  choiceOn: { borderColor: color.accent, backgroundColor: color.accentWash },
  choiceText: { flex: 1 },
  choiceLabel: { fontWeight: '600' },
  radio: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: color.lineStrong,
  },
  radioOn: { borderWidth: 6, borderColor: color.accent },
  box: {
    width: 20,
    height: 20,
    borderRadius: radius.s - 2,
    borderWidth: 1.5,
    borderColor: color.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  boxOn: { backgroundColor: color.accent, borderColor: color.accent },
});
