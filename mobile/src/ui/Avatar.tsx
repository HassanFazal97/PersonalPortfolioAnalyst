import { StyleSheet, View } from 'react-native';

import { color, radius } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

/** Header lettermark. Falls back to a dot rather than a blank circle. */
export function Avatar({ email, size = 34 }: { email?: string | null; size?: number }) {
  const initial = (email ?? '').trim().slice(0, 1).toUpperCase() || '·';
  return (
    <View
      style={[styles.root, { width: size, height: size, borderRadius: size / 2 }]}
      accessibilityLabel={email ? `Signed in as ${email}` : 'Account'}
    >
      <Txt variant="cardTitle" tone="accent">
        {initial}
      </Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: color.accentDeep,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
  },
});
