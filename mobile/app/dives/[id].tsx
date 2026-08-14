import { useLocalSearchParams, useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ScrollView } from 'react-native';

import { useDeepDive } from '@/api/reports';
import { dayLabel } from '@/format';
import { color, space, HIT_SLOP } from '@/theme/tokens';
import { Card, EmptyState, ErrorNote, SkeletonBlock, Tag, Txt } from '@/ui';

/**
 * One deep dive report. Also the landing screen for the
 * `cirvia://dives/{id}` push, which is why it polls a running dive rather
 * than assuming it was opened from the screen that started it.
 */
export default function DeepDiveScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data, isLoading, isError, refetch } = useDeepDive(id ?? '');

  const running = data?.status === 'running';

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.nav}>
        <Pressable onPress={() => router.back()} hitSlop={HIT_SLOP} accessibilityRole="button">
          <Txt variant="body" tone="accent">
            ‹ Back
          </Txt>
        </Pressable>
        <Txt variant="caption" tone="ink3">
          {data?.created_at ? dayLabel(data.created_at) : ''}
        </Txt>
        <View style={styles.navSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {isError ? (
          <ErrorNote message="Could not load this report." onRetry={() => void refetch()} />
        ) : null}

        {isLoading ? (
          <Card>
            <SkeletonBlock lines={5} />
          </Card>
        ) : null}

        {running ? (
          <Card title="Running">
            <Txt variant="bodySm" tone="ink2">
              A team of research agents is working through your portfolio. This usually
              takes a couple of minutes.
            </Txt>
            <Txt variant="caption" tone="ink3" style={styles.gap}>
              Safe to close the app — we&apos;ll notify you when it&apos;s ready.
            </Txt>
          </Card>
        ) : null}

        {data?.status === 'error' ? (
          <EmptyState
            title="This deep dive didn't finish"
            body="Nothing was charged against your limit. Start another from the Digest tab."
          />
        ) : null}

        {data?.summary && !running ? (
          <Card
            title="Summary"
            accessory={
              data.status === 'partial' ? <Tag label="Partial" tone="warn" /> : undefined
            }
          >
            <Txt variant="bodySm" tone="ink2">
              {data.summary}
            </Txt>
          </Card>
        ) : null}

        {data?.report && !running ? (
          <Card title="The full report">
            <Txt variant="bodySm" tone="ink2">
              {data.report}
            </Txt>
          </Card>
        ) : null}

        {data && !running ? (
          <Txt variant="caption" tone="ink3" center style={styles.gap}>
            Informational only. Cirvia never gives buy or sell advice.
          </Txt>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.s4,
    paddingVertical: space.s2,
  },
  navSpacer: { width: 56 },
  content: { paddingHorizontal: space.s4, paddingBottom: space.s9 },
  gap: { marginTop: space.s2 },
});
