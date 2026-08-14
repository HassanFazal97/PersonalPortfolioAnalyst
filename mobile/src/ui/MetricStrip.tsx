import { StyleSheet, View } from 'react-native';

import { color, radius, space } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type Metric = {
  label: string;
  value: string;
  /** Colours the value. `null` leaves it ink — a value that isn't a delta. */
  delta?: number | null;
};

/** `.dash-summary`: the three-up portfolio value / day / total return strip. */
export function MetricStrip({ metrics }: { metrics: Metric[] }) {
  return (
    <View style={styles.row}>
      {metrics.map((m) => (
        <View key={m.label} style={styles.cell}>
          <Txt variant="label" tone="ink3" uppercase>
            {m.label}
          </Txt>
          <Txt
            variant="metric"
            tone={m.delta == null ? 'ink' : m.delta >= 0 ? 'gain' : 'loss'}
            tabular
            adjustsFontSizeToFit
            numberOfLines={1}
            style={styles.value}
          >
            {m.value}
          </Txt>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: space.s2, marginBottom: space.s3 },
  cell: {
    flex: 1,
    backgroundColor: color.surface1,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.line,
    borderRadius: radius.m,
    paddingHorizontal: space.s3,
    paddingVertical: space.s2,
  },
  value: { marginTop: 3 },
});
