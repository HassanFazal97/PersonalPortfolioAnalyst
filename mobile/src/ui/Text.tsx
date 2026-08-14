import { Text as RNText, StyleSheet, type TextProps, type TextStyle } from 'react-native';

import { color, type } from '@/theme/tokens';

type Variant = keyof typeof type;
type Tone = 'ink' | 'ink2' | 'ink3' | 'accent' | 'gain' | 'loss' | 'warn' | 'inverse';

const TONES: Record<Tone, string> = {
  ink: color.ink,
  ink2: color.ink2,
  ink3: color.ink3,
  accent: color.accentText,
  gain: color.gain,
  loss: color.loss,
  warn: color.warnInk,
  inverse: color.white,
};

export type TxtProps = TextProps & {
  variant?: Variant;
  tone?: Tone;
  /** Line up digits in a column — market values, percentages, quantities. */
  tabular?: boolean;
  center?: boolean;
  uppercase?: boolean;
};

/**
 * Every piece of text in the app goes through here. Bare `<Text>` inherits
 * nothing on React Native, so a screen that reaches for it drifts off the
 * scale within a week.
 */
export function Txt({
  variant = 'body',
  tone = 'ink2',
  tabular,
  center,
  uppercase,
  style,
  ...rest
}: TxtProps) {
  return (
    <RNText
      style={[
        type[variant] as TextStyle,
        { color: TONES[tone] },
        tabular && styles.tabular,
        center && styles.center,
        uppercase && styles.uppercase,
        style,
      ]}
      {...rest}
    />
  );
}

const styles = StyleSheet.create({
  tabular: { fontVariant: ['tabular-nums'] },
  center: { textAlign: 'center' },
  uppercase: { textTransform: 'uppercase' },
});
