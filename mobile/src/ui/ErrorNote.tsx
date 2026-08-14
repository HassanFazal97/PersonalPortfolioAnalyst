import { StyleSheet, View } from 'react-native';

import { color, radius, space } from '@/theme/tokens';
import { Button } from '@/ui/Button';
import { Txt } from '@/ui/Text';

/**
 * An inline failure. Says what broke and offers the way out; never blanks a
 * panel that had working content a second ago — that decision lives in the
 * ETag layer, which keeps the last good value on an errored section.
 */
export function ErrorNote({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <View style={styles.root}>
      <Txt variant="bodySm" tone="loss">
        {message}
      </Txt>
      {onRetry ? <Button label="Try again" variant="link" onPress={onRetry} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: '#fbe3e0',
    borderRadius: radius.m,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.loss,
    padding: space.s3,
    marginBottom: space.s3,
    gap: space.s1,
  },
});
