import { useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { enablePush, markPrimed } from '@/push/register';
import { color, radius, space } from '@/theme/tokens';
import { Button, Card, ListRow, Txt } from '@/ui';

/**
 * The explainer that runs *before* the OS permission prompt.
 *
 * The system prompt can only be shown once. Spending it at first launch — on
 * a user with no portfolio, who has never seen a digest — is how an app ends
 * up with a permanently muted install base. This screen appears after the
 * first successful sync instead, when there is something concrete to promise.
 */
export default function PushPriming() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [busy, setBusy] = useState(false);

  const done = () => router.replace('/(tabs)');

  const turnOn = async () => {
    setBusy(true);
    await enablePush();
    setBusy(false);
    done();
  };

  const notNow = () => {
    // Recorded either way: asking twice is how the prompt gets wasted.
    markPrimed();
    done();
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.body}>
        <View style={styles.badge}>
          <Txt variant="title" tone="inverse">
            ✦
          </Txt>
        </View>

        <Txt variant="title" tone="ink">
          Want the brief on your phone?
        </Txt>
        <Txt variant="bodySm" tone="ink2" style={styles.lead}>
          Your morning digest is written before the market opens. We&apos;ll also ping you
          when a holding moves unusually, or when a deep dive you started finishes.
        </Txt>

        <Card>
          <ListRow title="Morning digest" subtitle="Weekdays, before the open" />
          <ListRow title="Unusual moves" subtitle="Only when the move is statistically odd" />
          <ListRow
            title="Deep dive ready"
            subtitle="When a report you started finishes"
            last
          />
        </Card>

        <Txt variant="caption" tone="ink3">
          You keep getting your digest by email either way, and you can turn any of these
          off in settings.
        </Txt>
      </View>

      <View style={[styles.footer, { paddingBottom: insets.bottom + space.s3 }]}>
        <Button label="Turn on notifications" onPress={turnOn} loading={busy} />
        <Button label="Not now" variant="ghost" onPress={notNow} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  body: { flex: 1, paddingHorizontal: space.s4, paddingTop: space.s7, gap: space.s3 },
  badge: {
    width: 60,
    height: 60,
    borderRadius: radius.l,
    backgroundColor: color.accent,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: space.s2,
  },
  lead: { marginBottom: space.s2 },
  footer: { paddingHorizontal: space.s4, gap: space.s2 },
});
