import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { color, space, MIN_TAP } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type TabItem<T extends string> = { key: T; label: string };

export type SegmentedTabsProps<T extends string> = {
  items: TabItem<T>[];
  value: T;
  onChange: (key: T) => void;
};

/**
 * `.dash-tabs`: an underlined tab row that scrolls horizontally rather than
 * wrapping, so a fifth tab never pushes the content down a line.
 */
export function SegmentedTabs<T extends string>({
  items,
  value,
  onChange,
}: SegmentedTabsProps<T>) {
  return (
    <View style={styles.wrap}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
      >
        {items.map((item) => {
          const active = item.key === value;
          return (
            <Pressable
              key={item.key}
              onPress={() => onChange(item.key)}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              style={[styles.tab, active && styles.tabActive]}
            >
              <Txt variant="bodySm" tone={active ? 'accent' : 'ink3'} style={styles.label}>
                {item.label}
              </Txt>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.line,
    marginBottom: space.s3,
  },
  row: { paddingHorizontal: space.s4, gap: space.s5 },
  tab: {
    minHeight: MIN_TAP - 8,
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: { borderBottomColor: color.accent },
  label: { fontWeight: '600' },
});
