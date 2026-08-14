import { StyleSheet, View } from 'react-native';

import { color, space } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type MetricListItem = {
  label: string;
  value: string;
  /** Glance cue on the value only — the label never changes colour. */
  tone?: 'ink' | 'gain' | 'loss' | 'warn';
};

/** `.metric-list`: a compact label/value ledger inside a card. */
export function MetricList({ items }: { items: MetricListItem[] }) {
  if (!items.length) {
    return (
      <Txt variant="caption" tone="ink3">
        No data available.
      </Txt>
    );
  }
  return (
    <View>
      {items.map((item, i) => (
        <View key={`${item.label}-${i}`} style={[styles.row, i === 0 && styles.first]}>
          <Txt variant="caption" tone="ink3" style={styles.label} numberOfLines={1}>
            {item.label}
          </Txt>
          <Txt variant="bodySm" tone={item.tone ?? 'ink'} tabular>
            {item.value}
          </Txt>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.s3,
    paddingVertical: space.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.line,
  },
  first: { borderTopWidth: 0 },
  label: { flexShrink: 1 },
});
