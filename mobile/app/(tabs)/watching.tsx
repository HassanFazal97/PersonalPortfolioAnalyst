import { useRouter } from 'expo-router';
import { useMemo } from 'react';

import { useDashboard } from '@/api/bootstrap';
import { fmtNum, fmtSignedPct } from '@/format';
import { pieColors } from '@/theme/tokens';
import { Card, EmptyState, ErrorNote, ListRow, Screen, SkeletonBlock, Txt } from '@/ui';

export default function WatchingTab() {
  const router = useRouter();
  const { data, isFetching, refetch } = useDashboard();
  const section = data?.sections.watchlist;

  // Held tickers already appear under Holdings; Watching is for the ones the
  // user follows without owning, same split as the web tab.
  const items = useMemo(
    () => (section?.value?.items ?? []).filter((i) => !i.held),
    [section?.value?.items],
  );

  return (
    <Screen
      title="Watching"
      subtitle={items.length ? `${items.length} stock${items.length === 1 ? '' : 's'}` : undefined}
      onRefresh={() => void refetch()}
      refreshing={isFetching}
    >
      {section?.error && !section.value ? (
        <ErrorNote message="Your watchlist could not be loaded." onRetry={() => void refetch()} />
      ) : null}

      {!data ? (
        <Card>
          <SkeletonBlock lines={3} />
        </Card>
      ) : null}

      {items.length ? (
        <Card>
          <Txt variant="caption" tone="ink3">
            Stocks you follow without holding them: news coverage, a digest line, and
            unusual-move alerts.
          </Txt>
          {items.map((item, i) => (
            <ListRow
              key={item.ticker}
              title={item.ticker}
              value={fmtNum(item.last_price)}
              meta={fmtSignedPct(item.day_change_pct)}
              delta={item.day_change_pct}
              markColor={pieColors[i % pieColors.length]}
              onPress={() => router.push(`/stock/${item.ticker}`)}
              last={i === items.length - 1}
            />
          ))}
        </Card>
      ) : data ? (
        <EmptyState
          title="Not watching anything yet"
          body="Add a stock you don't own and Cirvia covers it in your digest, news, and alerts."
        />
      ) : null}
    </Screen>
  );
}
