import type { ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { color, radius, space } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type CardProps = {
  children?: ReactNode;
  title?: string;
  /** Right-hand side of the title row: a tag, a timestamp, a small action. */
  accessory?: ReactNode;
  style?: StyleProp<ViewStyle>;
  /** Drop the inner padding when the card holds a full-bleed list. */
  flush?: boolean;
};

/** `.dash-card`: a near-white panel that lifts off the tinted canvas. */
export function Card({ children, title, accessory, style, flush }: CardProps) {
  return (
    <View style={[styles.card, flush && styles.flush, style]}>
      {title || accessory ? (
        <View style={[styles.head, flush && styles.headFlush]}>
          {title ? (
            <Txt variant="cardTitle" tone="ink" style={styles.title}>
              {title}
            </Txt>
          ) : (
            <View style={styles.title} />
          )}
          {accessory}
        </View>
      ) : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: color.surface1,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.line,
    borderRadius: radius.l,
    padding: space.s3,
    marginBottom: space.s3,
  },
  flush: { paddingHorizontal: 0, paddingVertical: space.s1 },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.s2,
    marginBottom: space.s2,
  },
  headFlush: { paddingHorizontal: space.s3, marginTop: space.s2 },
  title: { flexShrink: 1 },
});
