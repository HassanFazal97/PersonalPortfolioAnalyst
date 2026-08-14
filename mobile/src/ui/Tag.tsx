import { StyleSheet, View } from 'react-native';

import { color, radius, space } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type TagTone = 'accent' | 'neutral' | 'gain' | 'loss' | 'warn';

const FILLS: Record<TagTone, string> = {
  accent: color.accentDeep,
  neutral: color.surface2,
  gain: '#dff0e4',
  loss: '#fbe3e0',
  warn: color.warnBg,
};

const INKS: Record<TagTone, string> = {
  accent: color.accentText,
  neutral: color.ink3,
  gain: color.gain,
  loss: color.loss,
  warn: color.warnInk,
};

/** `.tag`: the small uppercase pill used for Pro, severity, and counts. */
export function Tag({ label, tone = 'accent' }: { label: string; tone?: TagTone }) {
  return (
    <View style={[styles.tag, { backgroundColor: FILLS[tone] }]}>
      <Txt variant="label" uppercase style={{ color: INKS[tone] }}>
        {label}
      </Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  tag: {
    borderRadius: radius.pill,
    paddingHorizontal: space.s2,
    paddingVertical: 3,
    alignSelf: 'flex-start',
  },
});
