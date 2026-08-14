import { useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useCallback, useEffect, useRef, useState } from 'react';
import { View } from 'react-native';

import { fetchConnectUrl, useBrokerageStatus, useSyncPortfolio } from '@/api/onboarding';
import { ApiError } from '@/api/client';
import { Step } from '@/onboarding/Step';
import { hasBeenPrimed, isFreeBuild } from '@/push/register';
import { space } from '@/theme/tokens';
import { Button, Card, ErrorNote, MetricList, Txt } from '@/ui';

type Phase = 'idle' | 'opening' | 'waiting' | 'syncing' | 'done';

/** How long to keep polling after the portal closes before giving up. */
const POLL_MS = 3000;
const POLL_LIMIT = 20;

/**
 * Steps 2 and 3 in one screen: link the brokerage, then pull holdings.
 *
 * The portal opens in an `ASWebAuthenticationSession` (Custom Tabs on
 * Android), never an embedded WebView — brokerage identity providers block
 * those outright. There is no server callback in this flow, so completion is
 * detected by polling `/portfolio/status` and then syncing.
 */
export default function ConnectStep() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const pollsRef = useRef(0);

  const status = useBrokerageStatus(phase === 'waiting');
  const sync = useSyncPortfolio();

  const runSync = useCallback(async () => {
    setPhase('syncing');
    try {
      await sync.mutateAsync();
      setPhase('done');
      // The permission prompt is a one-shot resource, so it is spent here —
      // right after the first successful sync, when there is finally a real
      // portfolio to promise a digest about — and never at launch.
      if (!hasBeenPrimed() && !isFreeBuild()) router.push('/push-priming');
      else router.push('/(onboarding)/risk');
    } catch (e) {
      setPhase('idle');
      setError(
        e instanceof ApiError
          ? e.detail
          : 'Your brokerage connected, but the first sync failed. Try again.',
      );
    }
  }, [router, sync]);

  // Poll while waiting for the portal round-trip to land.
  //
  // Depends on `refetch`, not the query object: the latter gets a new identity
  // on every render, which would re-create the interval and reset the attempt
  // counter continuously — the give-up branch would then never be reached.
  const { refetch } = status;
  useEffect(() => {
    if (phase !== 'waiting') return;
    pollsRef.current = 0;
    const timer = setInterval(() => {
      pollsRef.current += 1;
      if (pollsRef.current > POLL_LIMIT) {
        clearInterval(timer);
        setPhase('idle');
        setError(
          "We didn't see a completed connection. If you finished in the portal, tap Connect again.",
        );
        return;
      }
      void refetch();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [phase, refetch]);

  useEffect(() => {
    if (phase === 'waiting' && status.data?.connected) {
      void runSync();
    }
  }, [phase, status.data?.connected, runSync]);

  const connect = async () => {
    setError(null);
    setPhase('opening');
    try {
      const url = await fetchConnectUrl();
      // Returns when the user dismisses the sheet; the result carries no
      // completion signal because SnapTrade has no callback here, so the
      // status poll is what actually decides.
      await WebBrowser.openAuthSessionAsync(url, 'cirvia://onboarding/connected');
      setPhase('waiting');
    } catch (e) {
      setPhase('idle');
      setError(
        e instanceof ApiError
          ? e.detail
          : 'Could not open the brokerage portal. Check your connection and try again.',
      );
    }
  };

  const busy = phase === 'opening' || phase === 'waiting' || phase === 'syncing';

  return (
    <Step
      step={2}
      title="Connect your brokerage"
      blurb="Read-only, through SnapTrade. Cirvia never sees your login and can never place a trade."
      onSkip={() => router.push('/(onboarding)/risk')}
      skipLabel="Later"
      footer={
        <>
          <Button
            label={phase === 'waiting' ? 'Waiting for the portal…' : 'Connect a brokerage'}
            onPress={connect}
            loading={busy}
          />
          <Button
            label="Enter my holdings manually"
            variant="ghost"
            onPress={() => router.push('/(onboarding)/manual')}
          />
        </>
      }
    >
      {error ? <ErrorNote message={error} /> : null}

      {phase === 'syncing' ? (
        <Card>
          <Txt variant="bodySm" tone="ink">
            Pulling your positions…
          </Txt>
          <Txt variant="caption" tone="ink3">
            This takes a few seconds.
          </Txt>
        </Card>
      ) : null}

      <Card title="What Cirvia can see">
        <MetricList
          items={[
            { label: 'Your positions and quantities', value: 'Yes' },
            { label: 'Account balances', value: 'Yes' },
            { label: 'Your brokerage password', value: 'Never' },
            { label: 'Ability to trade', value: 'Never' },
          ]}
        />
      </Card>

      <View style={styles.note}>
        <Txt variant="caption" tone="ink3">
          A brokerage window will open. Come back here when you&apos;re done and we&apos;ll
          pick it up automatically.
        </Txt>
      </View>
    </Step>
  );
}

const styles = { note: { marginTop: space.s2 } } as const;
