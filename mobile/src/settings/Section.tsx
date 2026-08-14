import { useRouter } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { color, radius, space, HIT_SLOP, MIN_TAP } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

/** Frame for a settings sub-screen: back nav, title, scrolling body. */
export function SettingsScreen({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.nav}>
        <Pressable onPress={() => router.back()} hitSlop={HIT_SLOP} accessibilityRole="button">
          <Txt variant="body" tone="accent">
            ‹ Settings
          </Txt>
        </Pressable>
        <Txt variant="cardTitle" tone="ink">
          {title}
        </Txt>
        <View style={styles.navSpacer} />
      </View>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
    </View>
  );
}

/** A grouped list, iOS-style: rounded, hairline-separated, one topic each. */
export function Group({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <View style={styles.groupWrap}>
      {label ? (
        <Txt variant="label" tone="ink3" uppercase style={styles.groupLabel}>
          {label}
        </Txt>
      ) : null}
      <View style={styles.group}>{children}</View>
    </View>
  );
}

export function Row({
  label,
  value,
  hint,
  onPress,
  destructive,
  right,
}: {
  label: string;
  value?: string;
  hint?: string;
  onPress?: () => void;
  destructive?: boolean;
  right?: ReactNode;
}) {
  const body = (
    <View style={styles.row}>
      <View style={styles.rowMain}>
        <Txt variant="bodySm" tone={destructive ? 'loss' : 'ink'}>
          {label}
        </Txt>
        {hint ? (
          <Txt variant="caption" tone="ink3">
            {hint}
          </Txt>
        ) : null}
      </View>
      {value ? (
        <Txt variant="caption" tone="ink3" numberOfLines={1} style={styles.rowValue}>
          {value}
        </Txt>
      ) : null}
      {right}
      {onPress ? (
        <Txt variant="body" tone="ink3">
          ›
        </Txt>
      ) : null}
    </View>
  );

  if (!onPress) return body;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => pressed && styles.pressed}
    >
      {body}
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
  navSpacer: { width: 72 },
  content: { paddingHorizontal: space.s4, paddingBottom: space.s9 },
  groupWrap: { marginBottom: space.s4 },
  groupLabel: { marginBottom: space.s2, marginLeft: space.s1 },
  group: {
    backgroundColor: color.surface1,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.line,
    borderRadius: radius.l,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.s3,
    minHeight: MIN_TAP,
    paddingHorizontal: space.s3,
    paddingVertical: space.s3,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.line,
  },
  rowMain: { flex: 1 },
  rowValue: { flexShrink: 1, maxWidth: '45%', textAlign: 'right' },
  pressed: { backgroundColor: color.surface2 },
});
