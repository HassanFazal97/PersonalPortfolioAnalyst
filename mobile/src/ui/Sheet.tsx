import type { ReactNode } from 'react';
import { Modal, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { color, elevation, radius, space } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

export type SheetProps = {
  visible: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
};

/**
 * Bottom sheet for filters, pickers, and confirmations. Backed by `Modal` so
 * it sits above the tab bar and takes the hardware back button on Android.
 */
export function Sheet({ visible, onClose, title, children }: SheetProps) {
  const insets = useSafeAreaInsets();
  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      {/* The scrim is a real dismiss target, so it announces as a button
          rather than as an unlabelled view a screen reader walks past. */}
      <Pressable
        style={styles.scrim}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + space.s5 }]}>
        <View style={styles.grab} />
        {title ? (
          <Txt variant="heading" tone="ink" style={styles.title}>
            {title}
          </Txt>
        ) : null}
        {children}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, backgroundColor: 'rgba(36, 30, 48, 0.42)' },
  sheet: {
    backgroundColor: color.surface1,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: space.s4,
    paddingTop: space.s2,
    ...elevation.sheet,
  },
  grab: {
    width: 38,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: color.lineStrong,
    alignSelf: 'center',
    marginBottom: space.s3,
  },
  title: { marginBottom: space.s3 },
});
