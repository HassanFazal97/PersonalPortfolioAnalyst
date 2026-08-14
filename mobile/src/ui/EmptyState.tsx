import { StyleSheet, View } from 'react-native';

import { space } from '@/theme/tokens';
import { Button } from '@/ui/Button';
import { Txt } from '@/ui/Text';

export type EmptyStateProps = {
  title: string;
  body?: string;
  actionLabel?: string;
  onAction?: () => void;
};

/**
 * The "nothing here yet" block. Always says what will fill the space and
 * when — never a bare "No data".
 */
export function EmptyState({ title, body, actionLabel, onAction }: EmptyStateProps) {
  return (
    <View style={styles.root}>
      <Txt variant="heading" tone="ink" center>
        {title}
      </Txt>
      {body ? (
        <Txt variant="bodySm" tone="ink3" center>
          {body}
        </Txt>
      ) : null}
      {actionLabel && onAction ? (
        <View style={styles.action}>
          <Button label={actionLabel} onPress={onAction} variant="ghost" block={false} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    alignItems: 'center',
    gap: space.s2,
    paddingVertical: space.s7,
    paddingHorizontal: space.s4,
  },
  action: { marginTop: space.s2 },
});
