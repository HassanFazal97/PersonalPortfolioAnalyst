import { useRouter } from 'expo-router';

import { useDeepDives, useStartDeepDive } from '@/api/reports';
import { ApiError } from '@/api/client';
import { dayLabel } from '@/format';
import { Group, Row, SettingsScreen } from '@/settings/Section';
import { space } from '@/theme/tokens';
import { Button, Card, EmptyState, ErrorNote, SkeletonBlock, Txt } from '@/ui';

export default function DeepDivesScreen() {
  const router = useRouter();
  const { data, isLoading, refetch } = useDeepDives();
  const start = useStartDeepDive();

  const reports = data?.reports ?? [];

  const run = async () => {
    try {
      const { report_id } = await start.mutateAsync();
      router.push(`/dives/${report_id}`);
    } catch {
      // Surfaced below: 402/429 carry the server's own copy.
    }
  };

  return (
    <SettingsScreen title="Deep dives">
      {start.isError ? (
        <ErrorNote
          message={
            start.error instanceof ApiError
              ? start.error.detail
              : 'Could not start a deep dive.'
          }
        />
      ) : null}

      <Card>
        <Txt variant="bodySm" tone="ink2">
          Fundamentals, technical, risk, and news agents research your portfolio in
          parallel. A verifier then re-checks every claim against live data before the
          report is written.
        </Txt>
      </Card>

      <Button label="Run a deep dive" onPress={run} loading={start.isPending} />

      {isLoading ? (
        <Card>
          <SkeletonBlock lines={3} />
        </Card>
      ) : null}

      {reports.length ? (
        <Group label="Past reports">
          {reports.map((r) => (
            <Row
              key={r.report_id}
              label={r.summary?.slice(0, 60) || 'Deep dive'}
              hint={r.created_at ? dayLabel(r.created_at) : undefined}
              value={r.status === 'running' ? 'Running' : undefined}
              onPress={() => router.push(`/dives/${r.report_id}`)}
            />
          ))}
        </Group>
      ) : !isLoading ? (
        <EmptyState
          title="No reports yet"
          body="Your first deep dive takes a couple of minutes and lands here."
          actionLabel="Refresh"
          onAction={() => void refetch()}
        />
      ) : null}

      <Txt variant="caption" tone="ink3" center style={styles.note}>
        Informational only. Cirvia never gives buy or sell advice.
      </Txt>
    </SettingsScreen>
  );
}

const styles = { note: { marginTop: space.s3 } } as const;
