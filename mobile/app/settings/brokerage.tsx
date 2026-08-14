import { useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useState } from 'react';

import { useDashboard } from '@/api/bootstrap';
import { ApiError } from '@/api/client';
import { fetchConnectUrl, useBrokerageStatus, useSyncPortfolio } from '@/api/onboarding';
import { timeLabel } from '@/format';
import { Group, Row, SettingsScreen } from '@/settings/Section';
import { space } from '@/theme/tokens';
import { Button, ErrorNote, Txt } from '@/ui';

export default function BrokerageScreen() {
  const router = useRouter();
  const { data } = useDashboard();
  const status = useBrokerageStatus();
  const sync = useSyncPortfolio();
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  const s = status.data ?? data?.sections.status.value ?? null;

  const reconnect = async () => {
    setError(null);
    setOpening(true);
    try {
      const url = await fetchConnectUrl();
      await WebBrowser.openAuthSessionAsync(url, 'cirvia://settings/brokerage');
      await status.refetch();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Could not open the brokerage portal.');
    } finally {
      setOpening(false);
    }
  };

  const runSync = async () => {
    setError(null);
    try {
      await sync.mutateAsync();
      await status.refetch();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Sync failed. Try again in a minute.');
    }
  };

  return (
    <SettingsScreen title="Brokerage">
      {error ? <ErrorNote message={error} /> : null}
      {s?.last_sync_error ? <ErrorNote message={s.last_sync_error} /> : null}

      <Group label="Connection">
        <Row
          label="Status"
          value={
            s?.connected
              ? 'Connected'
              : s?.connection_disabled
                ? 'Needs reconnecting'
                : s?.registered
                  ? 'Not linked'
                  : 'Not set up'
          }
        />
        <Row label="Accounts" value={String(s?.accounts_count ?? 0)} />
        <Row
          label="Last sync"
          value={s?.last_sync_at ? timeLabel(s.last_sync_at) : 'Never'}
        />
      </Group>

      <Button
        label={s?.connected ? 'Sync now' : 'Connect a brokerage'}
        onPress={s?.connected ? runSync : reconnect}
        loading={sync.isPending || opening}
      />

      {s?.connected ? (
        <Button label="Reconnect a brokerage" variant="ghost" onPress={reconnect} loading={opening} />
      ) : null}

      <Button
        label="Enter holdings manually"
        variant="ghost"
        onPress={() => router.push('/(onboarding)/manual')}
      />

      <Txt variant="caption" tone="ink3" style={styles.note}>
        Cirvia connects read-only through SnapTrade. It never sees your brokerage login and
        can never place a trade.
      </Txt>
    </SettingsScreen>
  );
}

const styles = { note: { marginTop: space.s3 } } as const;
