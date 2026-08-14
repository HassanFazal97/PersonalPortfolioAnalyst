import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { color, radius, space, MIN_TAP } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type ListRowProps = {
  title: string;
  subtitle?: string;
  /** Right-hand primary value — a market value, a count, a setting's state. */
  value?: string;
  /** Secondary line under the value; coloured by `delta`. */
  meta?: string;
  delta?: number | null;
  /** Square lettermark, coloured to match the allocation donut. */
  markColor?: string;
  markLabel?: string;
  leading?: ReactNode;
  onPress?: () => void;
  last?: boolean;
};

/**
 * One row of a holdings / watchlist / settings list. The whole row is the tap
 * target, matching the web table where the row navigates and the ticker
 * anchor only exists to keep middle-click working.
 */
export function ListRow({
  title,
  subtitle,
  value,
  meta,
  delta,
  markColor,
  markLabel,
  leading,
  onPress,
  last,
}: ListRowProps) {
  const content = (
    <View style={[styles.row, last && styles.last]}>
      {leading}
      {!leading && markColor ? (
        <View style={[styles.mark, { backgroundColor: markColor }]}>
          <Txt variant="label" tone="inverse">
            {(markLabel ?? title).slice(0, 1).toUpperCase()}
          </Txt>
        </View>
      ) : null}
      <View style={styles.main}>
        <Txt variant="cardTitle" tone="ink" numberOfLines={1}>
          {title}
        </Txt>
        {subtitle ? (
          <Txt variant="caption" tone="ink3" tabular numberOfLines={1}>
            {subtitle}
          </Txt>
        ) : null}
      </View>
      {value || meta ? (
        <View style={styles.end}>
          {value ? (
            <Txt variant="cardTitle" tone="ink" tabular>
              {value}
            </Txt>
          ) : null}
          {meta ? (
            <Txt
              variant="caption"
              tone={delta == null ? 'ink3' : delta >= 0 ? 'gain' : 'loss'}
              tabular
            >
              {meta}
            </Txt>
          ) : null}
        </View>
      ) : null}
      {onPress ? (
        <Txt variant="body" tone="ink3" style={styles.chev}>
          ›
        </Txt>
      ) : null}
    </View>
  );

  if (!onPress) return content;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${title}${value ? `, ${value}` : ''}`}
      style={({ pressed }) => pressed && styles.pressed}
    >
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.s3,
    minHeight: MIN_TAP,
    paddingVertical: space.s2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.line,
  },
  last: { borderBottomWidth: 0 },
  pressed: { backgroundColor: color.surface2, borderRadius: radius.s },
  mark: {
    width: 30,
    height: 30,
    borderRadius: radius.s,
    alignItems: 'center',
    justifyContent: 'center',
  },
  main: { flex: 1, minWidth: 0 },
  end: { alignItems: 'flex-end' },
  chev: { marginLeft: space.s1 },
});
