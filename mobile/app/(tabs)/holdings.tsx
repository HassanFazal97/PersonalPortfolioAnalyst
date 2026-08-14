import { useRouter } from 'expo-router';
import { useMemo } from 'react';

import { useDashboard } from '@/api/bootstrap';
import { Donut } from '@/dashboard/Donut';
import { allocationSlices, groupByTicker, mvCad } from '@/dashboard/portfolio';
import { fmtCurCompact, fmtSignedPct, timeLabel } from '@/format';
import { pieColors } from '@/theme/tokens';
import {
  Card,
  EmptyState,
  ErrorNote,
  ListRow,
  Screen,
  SkeletonBlock,
  Txt,
} from '@/ui';

export default function HoldingsTab() {
  const router = useRouter();
  const { data, isFetching, refetch } = useDashboard();
  const section = data?.sections.portfolio;
  const portfolio = section?.value ?? null;
  const status = data?.sections.status.value ?? null;

  const holdings = useMemo(
    () =>
      groupByTicker(portfolio?.positions ?? []).sort(
        (a, b) => (b.marketValue ?? 0) - (a.marketValue ?? 0),
      ),
    [portfolio?.positions],
  );

  const allocation = useMemo(
    () => allocationSlices(portfolio?.positions ?? [], portfolio?.totals ?? {}),
    [portfolio?.positions, portfolio?.totals],
  );

  const total = portfolio?.totals.total_market_value_cad;

  return (
    <Screen
      title="Holdings"
      subtitle={
        status?.last_sync_at ? `Synced ${timeLabel(status.last_sync_at)}` : undefined
      }
      onRefresh={() => void refetch()}
      refreshing={isFetching}
    >
      {section?.error && !portfolio ? (
        <ErrorNote
          message="Holdings could not be loaded."
          onRetry={() => void refetch()}
        />
      ) : null}

      {!data ? (
        <Card>
          <SkeletonBlock lines={4} />
        </Card>
      ) : null}

      {allocation.slices.length ? (
        <Card title="Allocation">
          <Donut slices={allocation.slices} count={allocation.priced} />
          {allocation.excluded > 0 ? (
            <Txt variant="caption" tone="ink3">
              {allocation.excluded} unpriced position
              {allocation.excluded === 1 ? '' : 's'} not shown.
            </Txt>
          ) : null}
        </Card>
      ) : null}

      {holdings.length ? (
        <Card
          title={`${holdings.length} position${holdings.length === 1 ? '' : 's'}`}
          accessory={
            <Txt variant="caption" tone="ink3" tabular>
              {fmtCurCompact(total)}
            </Txt>
          }
        >
          {holdings.map((h, i) => (
            <ListRow
              key={h.ticker}
              title={h.ticker}
              subtitle={
                `${Number(h.quantity.toFixed(6))} sh` +
                (h.accounts > 1 ? ` · ${h.accounts} accounts` : '')
              }
              value={fmtCurCompact(mvCad(h, portfolio?.totals ?? {}))}
              meta={fmtSignedPct(h.dayChangePct)}
              delta={h.dayChangePct}
              markColor={pieColors[i % pieColors.length]}
              onPress={() => router.push(`/stock/${h.ticker}`)}
              last={i === holdings.length - 1}
            />
          ))}
        </Card>
      ) : data ? (
        <EmptyState
          title="No holdings yet"
          body={
            status?.registered
              ? 'Your next sync will fill this in.'
              : 'Connect your brokerage on cirvia.ca and your positions appear here.'
          }
        />
      ) : null}
    </Screen>
  );
}
