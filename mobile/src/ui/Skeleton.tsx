import { useEffect } from 'react';
import { AccessibilityInfo, StyleSheet, View } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  cancelAnimation,
} from 'react-native-reanimated';

import { color, radius, space } from '@/theme/tokens';

/** `.skl`: a shimmering placeholder line. `short` renders the ragged last row. */
export function Skeleton({ short, style }: { short?: boolean; style?: object }) {
  const opacity = useSharedValue(0.6);

  useEffect(() => {
    let cancelled = false;
    AccessibilityInfo.isReduceMotionEnabled().then((reduced) => {
      if (cancelled || reduced) return;
      opacity.value = withRepeat(withTiming(1, { duration: 900 }), -1, true);
    });
    return () => {
      cancelled = true;
      cancelAnimation(opacity);
    };
  }, [opacity]);

  const animated = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <Animated.View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.line, short && styles.short, animated, style]}
    />
  );
}

/** The three-line block the web shows while a card's data is in flight. */
export function SkeletonBlock({ lines = 3 }: { lines?: number }) {
  return (
    <View style={styles.block}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} short={i === lines - 1} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: space.s2 },
  line: {
    height: 12,
    borderRadius: radius.s,
    backgroundColor: color.surface3,
  },
  short: { width: '58%' },
});
