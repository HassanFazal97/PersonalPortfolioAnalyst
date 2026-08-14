import { useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { BOOTSTRAP_PATH, useDashboard } from '@/api/bootstrap';
import { api } from '@/api/client';
import { invalidateCached } from '@/api/etag';
import { useIsOffline } from '@/api/online';
import { selectBanners, type BannerId } from '@/dashboard/banners';
import { summarize } from '@/dashboard/portfolio';
import { digestRuns, fmtCurCompact, fmtSignedCur, fmtSignedPct, timeLabel } from '@/format';
import { prefs } from '@/api/storage';
import { space, HIT_SLOP } from '@/theme/tokens';
import {
  Avatar,
  Banner,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  MetricStrip,
  Screen,
  SkeletonBlock,
  Txt,
} from '@/ui';

const DISMISS_KEY = 'banners:dismissed';

export default function DigestTab() {
  const router = useRouter();
  const { data, isFetching, refetch, error } = useDashboard();
  const offline = useIsOffline();
  const [dismissed, setDismissed] = useState<Set<BannerId>>(() => {
    const raw = prefs.getString(DISMISS_KEY);
    return new Set(raw ? (JSON.parse(raw) as BannerId[]) : []);
  });

  const dismiss = useCallback((id: BannerId) => {
    setDismissed((prev) => {
      const next = new Set(prev).add(id);
      prefs.set(DISMISS_KEY, JSON.stringify([...next]));
      return next;
    });
  }, []);

  /**
   * The one billing call the app is allowed to make. Choosing Free is not a
   * purchase — it unblocks a user stuck in the trial-decision gate with their
   * digests paused, which is otherwise a dead end inside the app.
   */
  const chooseFree = useCallback(async () => {
    try {
      await api('/billing/choose-free', { method: 'POST' });
      invalidateCached(BOOTSTRAP_PATH);
      await refetch();
    } catch {
      // Advisory: the banner stays up and the user can try again.
    }
  }, [refetch]);

  const me = data?.sections.me.value;
  const digest = data?.sections.digest;
  const portfolio = data?.sections.portfolio;
  const summary = useMemo(() => summarize(portfolio?.value ?? null), [portfolio?.value]);
  const banners = useMemo(() => selectBanners(data, dismissed), [data, dismissed]);

  const planLabel = me?.trial.active
    ? 'Pro trial'
    : (me?.effective_plan ?? me?.plan) === 'pro'
      ? 'Pro'
      : 'Free';

  const today = new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });

  return (
    <Screen
      title="Digest"
      subtitle={me ? `${today} · ${planLabel}` : today}
      headerRight={
        <Pressable
          onPress={() => router.push('/settings')}
          accessibilityRole="button"
          accessibilityLabel="Settings"
          hitSlop={HIT_SLOP}
        >
          <Avatar email={me?.email} />
        </Pressable>
      }
      onRefresh={() => void refetch()}
      refreshing={isFetching}
    >
      {/* Cached data keeps rendering underneath; this only explains why the
          numbers are not moving. */}
      {offline ? (
        <Banner
          tone="warn"
          title="You're offline."
          body="Showing the last data this device downloaded."
        />
      ) : null}

      {banners.map((b) => (
        <Banner
          key={b.id}
          tone={b.tone}
          title={b.title}
          body={b.body}
          // Only the trial banner has somewhere to go in this build: choosing
          // Free is a plain API call, while the other three point at settings
          // and onboarding screens that land in M4/M5. A button that goes
          // nowhere is worse than no button, so they show the text only.
          actionLabel={b.id === 'trial' ? b.actionLabel : undefined}
          onAction={b.id === 'trial' ? chooseFree : undefined}
          onDismiss={b.dismissible ? () => dismiss(b.id) : undefined}
          dismissLabel={b.id === 'personalize' ? 'Maybe later' : 'Dismiss'}
        />
      ))}

      <MetricStrip
        metrics={[
          { label: 'Value', value: fmtCurCompact(summary.value) },
          {
            label: 'Day',
            value: summary.dayPnl == null ? '–' : fmtSignedCur(summary.dayPnl),
            delta: summary.dayPnl,
          },
          {
            label: 'Total',
            value: fmtSignedPct(summary.totalPct),
            delta: summary.totalPct,
          },
        ]}
      />

      {portfolio?.error && !portfolio.value ? (
        <ErrorNote message="Portfolio values are unavailable right now." onRetry={() => void refetch()} />
      ) : null}

      {digest?.error && !digest.value ? (
        <ErrorNote message="Today's digest could not be loaded." onRetry={() => void refetch()} />
      ) : null}

      {!data && !error ? (
        <Card>
          <SkeletonBlock lines={5} />
        </Card>
      ) : null}

      {digest?.value ? (
        <Card
          title="Today's digest"
          accessory={
            <Txt variant="caption" tone="ink3">
              {timeLabel(digest.value.generated_at)}
            </Txt>
          }
        >
          <DigestBody body={digest.value.body} />
        </Card>
      ) : data ? (
        <EmptyState
          title="No digest yet today"
          body="Your morning brief lands here before the market opens."
        />
      ) : null}

      {data ? (
        <Txt variant="caption" tone="ink3" center style={styles.disclaimer}>
          Informational only. Cirvia never gives buy or sell advice.
        </Txt>
      ) : null}

      <View style={styles.askWrap}>
        <Button label="Ask Cirvia" onPress={() => router.push('/chat')} />
      </View>
    </Screen>
  );
}

/** Labelled plain-text sections, with the labels bolded — same as the web. */
function DigestBody({ body }: { body: string }) {
  const lines = useMemo(() => digestRuns(body), [body]);
  return (
    <View style={styles.digest}>
      {lines.map((runs, i) => (
        <Txt key={i} variant="bodySm" tone="ink2">
          {runs.map((run, j) => (
            <Txt
              key={j}
              variant="bodySm"
              tone={run.label ? 'ink' : 'ink2'}
              style={run.label ? styles.label : undefined}
            >
              {run.text}
            </Txt>
          ))}
        </Txt>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  digest: { gap: space.s2 },
  label: { fontWeight: '700' },
  disclaimer: { marginTop: space.s2 },
  askWrap: { marginTop: space.s4 },
});
