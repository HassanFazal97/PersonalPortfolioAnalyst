import type { ReactNode } from 'react';
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { color, space } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type ScreenProps = {
  children: ReactNode;
  /** Large iOS-style title. Omit on screens that use a stack header. */
  title?: string;
  subtitle?: string;
  /** Rendered opposite the title — avatar, action, count. */
  headerRight?: ReactNode;
  /** Pinned under the header, outside the scroll area (tabs, filters). */
  sticky?: ReactNode;
  onRefresh?: () => void;
  refreshing?: boolean;
  scroll?: boolean;
  contentStyle?: StyleProp<ViewStyle>;
};

/**
 * Page frame: safe-area padding, the title block, and pull-to-refresh.
 *
 * The bottom inset is deliberately not applied — the tab bar owns it — but
 * the scroll content gets enough tail padding to clear it.
 */
export function Screen({
  children,
  title,
  subtitle,
  headerRight,
  sticky,
  onRefresh,
  refreshing = false,
  scroll = true,
  contentStyle,
}: ScreenProps) {
  const insets = useSafeAreaInsets();

  const header = title ? (
    <View style={styles.header}>
      <View style={styles.headerText}>
        <Txt variant="display" tone="ink">
          {title}
        </Txt>
        {subtitle ? (
          <Txt variant="caption" tone="ink3" style={styles.subtitle}>
            {subtitle}
          </Txt>
        ) : null}
      </View>
      {headerRight}
    </View>
  ) : null;

  const body = scroll ? (
    <ScrollView
      style={styles.flex}
      contentContainerStyle={[styles.content, contentStyle]}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={color.accent}
            colors={[color.accent]}
          />
        ) : undefined
      }
    >
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.flex, styles.content, contentStyle]}>{children}</View>
  );

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      {header}
      {sticky}
      {body}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: space.s3,
    paddingHorizontal: space.s4,
    paddingTop: space.s2,
    paddingBottom: space.s3,
  },
  headerText: { flex: 1 },
  subtitle: { marginTop: 2 },
  content: {
    paddingHorizontal: space.s4,
    paddingBottom: space.s9,
  },
});
