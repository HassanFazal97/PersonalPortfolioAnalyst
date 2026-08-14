import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  RANGES,
  useStockDetail,
  useStockHistory,
  useStockNews,
  useWatchToggle,
  type RangeKey,
  type Verdict,
} from '@/api/stocks';
import { PriceChart } from '@/charts/PriceChart';
import { dayLabel, fmtCur, fmtNum, fmtPct, fmtSignedPct } from '@/format';
import { equityCards, etfCards, priceActionRows } from '@/stock/metrics';
import { color, radius, space, HIT_SLOP } from '@/theme/tokens';
import {
  Card,
  EmptyState,
  ErrorNote,
  MetricList,
  SkeletonBlock,
  Tag,
  Txt,
} from '@/ui';

export default function StockDetailScreen() {
  const { ticker: raw } = useLocalSearchParams<{ ticker: string }>();
  const ticker = (raw ?? '').toUpperCase();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [range, setRange] = useState<RangeKey>(182);

  const detail = useStockDetail(ticker);
  const history = useStockHistory(ticker, range);
  const news = useStockNews(ticker);
  const watch = useWatchToggle(ticker);

  const d = detail.data;
  const quoteType = (d?.profile.quote_type ?? '').toUpperCase();
  const cards = useMemo(() => {
    if (!d) return [];
    if (quoteType === 'ETF' || quoteType === 'MUTUALFUND') return etfCards(d);
    if (quoteType === 'EQUITY') return equityCards(d);
    return [];
  }, [d, quoteType]);

  const notFound = detail.error?.message === 'unknown ticker' || (detail.isError && !d);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.nav}>
        <Pressable onPress={() => router.back()} hitSlop={HIT_SLOP} accessibilityRole="button">
          <Txt variant="body" tone="accent">
            ‹ Back
          </Txt>
        </Pressable>
        {d ? (
          <Pressable
            onPress={() => watch.mutate(d.watching)}
            hitSlop={HIT_SLOP}
            disabled={watch.isPending}
            accessibilityRole="button"
            accessibilityLabel={d.watching ? `Stop watching ${ticker}` : `Watch ${ticker}`}
          >
            <Txt variant="body" tone="accent">
              {d.watching ? '★ Watching' : '☆ Watch'}
            </Txt>
          </Pressable>
        ) : null}
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Watching has a plan cap, so this can legitimately fail with a
            message the user needs to see — the server's own copy, minus the
            upgrade clause the client layer strips. */}
        {watch.isError ? (
          <ErrorNote
            message={
              watch.error instanceof Error
                ? watch.error.message
                : 'Could not update your watchlist.'
            }
          />
        ) : null}

        {notFound ? (
          <EmptyState
            title={`No data for ${ticker}`}
            body="That symbol didn't resolve to a tradable instrument."
            actionLabel="Go back"
            onAction={() => router.back()}
          />
        ) : null}

        {!d && !notFound ? (
          <Card>
            <SkeletonBlock lines={4} />
          </Card>
        ) : null}

        {d ? (
          <>
            <View style={styles.headline}>
              <Txt variant="title" tone="ink">
                {ticker}
              </Txt>
              {d.profile.name ? (
                <Txt variant="caption" tone="ink3" numberOfLines={1}>
                  {d.profile.name}
                </Txt>
              ) : null}
            </View>
            <View style={styles.priceRow}>
              <Txt variant="display" tone="ink" tabular>
                {fmtCur(d.quote.last_price, d.position?.currency ?? 'USD')}
              </Txt>
              <Txt
                variant="heading"
                tone={
                  d.quote.day_change_pct == null
                    ? 'ink3'
                    : d.quote.day_change_pct >= 0
                      ? 'gain'
                      : 'loss'
                }
                tabular
              >
                {fmtSignedPct(d.quote.day_change_pct)}
              </Txt>
            </View>

            <Card>
              {history.isError ? (
                <ErrorNote
                  message="Could not load price history."
                  onRetry={() => void history.refetch()}
                />
              ) : history.data ? (
                <PriceChart
                  bars={history.data.ohlcv ?? []}
                  intraday={Boolean(history.data.intraday)}
                  ticker={ticker}
                />
              ) : (
                <SkeletonBlock lines={3} />
              )}
              <View style={styles.ranges}>
                {RANGES.map((r) => {
                  const on = r.key === range;
                  return (
                    <Pressable
                      key={r.key}
                      onPress={() => setRange(r.key)}
                      accessibilityRole="button"
                      accessibilityState={{ selected: on }}
                      style={[styles.range, on && styles.rangeOn]}
                    >
                      <Txt variant="caption" tone={on ? 'inverse' : 'ink3'}>
                        {r.label}
                      </Txt>
                    </Pressable>
                  );
                })}
              </View>
            </Card>

            {d.position ? (
              <Card title="Your position">
                <MetricList
                  items={[
                    {
                      label: 'Market value',
                      value: fmtCur(d.position.market_value, d.position.currency),
                    },
                    {
                      label: `${Number(d.position.quantity.toFixed(6))} sh @ ${fmtNum(
                        d.position.avg_cost,
                      )}`,
                      value: fmtSignedPct(d.position.unrealized_pnl_pct),
                      tone:
                        d.position.unrealized_pnl_pct == null
                          ? undefined
                          : d.position.unrealized_pnl_pct >= 0
                            ? 'gain'
                            : 'loss',
                    },
                    { label: 'Share of portfolio', value: fmtPct(d.position.weight_pct) },
                  ]}
                />
              </Card>
            ) : null}

            {d.verdict ? <VerdictCard verdict={d.verdict} /> : null}

            {cards.map((card) => (
              <Card key={card.title} title={card.title}>
                <MetricList items={card.rows} />
              </Card>
            ))}

            {quoteType === 'EQUITY' || quoteType === 'ETF' || quoteType === 'MUTUALFUND' ? (
              <Card title="Price action">
                <Range52w
                  low={d.price_action?.low_52w ?? null}
                  high={d.price_action?.high_52w ?? null}
                  price={d.quote.last_price}
                />
                <MetricList items={priceActionRows(d)} />
              </Card>
            ) : (
              <Txt variant="caption" tone="ink3">
                Fundamentals aren&apos;t available for this instrument.
              </Txt>
            )}

            <Card title="News & digests">
              {news.data?.items?.length ? (
                news.data.items.slice(0, 8).map((item, i) => (
                  <View key={item.id ?? i} style={styles.newsItem}>
                    <Txt variant="caption" tone="ink3">
                      {dayLabel(item.published_at ?? item.created_at)}
                    </Txt>
                    {item.title ? (
                      <Txt variant="bodySm" tone="ink">
                        {item.title}
                      </Txt>
                    ) : null}
                    {item.body ? (
                      <Txt variant="caption" tone="ink2" numberOfLines={4}>
                        {item.body}
                      </Txt>
                    ) : null}
                  </View>
                ))
              ) : news.isLoading ? (
                <SkeletonBlock lines={2} />
              ) : (
                <Txt variant="caption" tone="ink3">
                  Nothing stored for {ticker} yet. Digests, alerts, and articles that mention
                  it will appear here.
                </Txt>
              )}
            </Card>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

/** The nightly "cheap or expensive" call. Label is free; evidence is Pro. */
function VerdictCard({ verdict }: { verdict: NonNullable<Verdict> }) {
  const tone =
    verdict.label === 'Undervalued' ? 'gain' : verdict.label === 'Expensive' ? 'loss' : 'neutral';
  const ev = verdict.evidence;
  const metrics = ev?.metrics ? Object.entries(ev.metrics) : [];

  const peerNote =
    ev?.sector_comparison === 'industry'
      ? `Vs. industry peers${ev.industry ? ` (${ev.industry})` : ''}`
      : ev?.sector_comparison === 'sector'
        ? `Vs. sector peers${ev.sector ? ` (${ev.sector})` : ''} — its industry group was too small to compare against alone`
        : 'Vs. the broader market — both its industry and sector groups were too small to compare against alone';

  return (
    <Card title="Valuation verdict" accessory={<Tag label={verdict.label} tone={tone} />}>
      {verdict.label === 'Not enough data' ? (
        verdict.not_scored_reason ? (
          <Txt variant="caption" tone="ink3">
            Not scored: {verdict.not_scored_reason}.
          </Txt>
        ) : null
      ) : verdict.evidence_gated ? (
        <Txt variant="caption" tone="ink3">
          Compared against industry peers today, falling back to sector, then the market, when
          there aren&apos;t enough industry peers. The numbers behind this verdict are part of
          Pro.
        </Txt>
      ) : (
        <>
          {metrics.length ? (
            <View style={styles.evidence}>
              <View style={styles.evHead}>
                <Txt variant="label" tone="ink3" uppercase style={styles.evMetric}>
                  metric
                </Txt>
                <Txt variant="label" tone="ink3" uppercase style={styles.evCol}>
                  this
                </Txt>
                <Txt variant="label" tone="ink3" uppercase style={styles.evCol}>
                  peers
                </Txt>
              </View>
              {metrics.map(([key, m]) => (
                <View key={key} style={styles.evRow}>
                  <Txt variant="caption" tone="ink" style={styles.evMetric}>
                    {key.replaceAll('_', ' ')}
                  </Txt>
                  <Txt variant="caption" tone="ink2" tabular style={styles.evCol}>
                    {String(m.value ?? '–')}
                  </Txt>
                  <Txt variant="caption" tone="ink2" tabular style={styles.evCol}>
                    {String(m.sector_median ?? '–')}
                  </Txt>
                </View>
              ))}
            </View>
          ) : null}
          <Txt variant="caption" tone="ink3">
            {peerNote}, {ev?.metrics_used ?? 0} metrics.
          </Txt>
        </>
      )}
    </Card>
  );
}

/** Where today's price sits in the 52-week range. */
function Range52w({
  low,
  high,
  price,
}: {
  low: number | null;
  high: number | null;
  price: number | null;
}) {
  if (low == null || high == null || price == null || high <= low) return null;
  const frac = Math.min(1, Math.max(0, (price - low) / (high - low)));
  return (
    <View style={styles.rangeBarWrap}>
      <View style={styles.rangeBar}>
        <View style={[styles.rangeDot, { left: `${frac * 100}%` as const }]} />
      </View>
      <View style={styles.rangeEnds}>
        <Txt variant="caption" tone="ink3" tabular>
          {fmtNum(low)}
        </Txt>
        <Txt variant="caption" tone="ink3">
          52-week range
        </Txt>
        <Txt variant="caption" tone="ink3" tabular>
          {fmtNum(high)}
        </Txt>
      </View>
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
  content: { paddingHorizontal: space.s4, paddingBottom: space.s9 },
  headline: { flexDirection: 'row', alignItems: 'baseline', gap: space.s2 },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: space.s3,
    marginBottom: space.s3,
  },
  ranges: { flexDirection: 'row', gap: space.s1, marginTop: space.s3 },
  range: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: space.s2,
    borderRadius: radius.s,
    backgroundColor: color.surface2,
  },
  rangeOn: { backgroundColor: color.accent },
  rangeBarWrap: { marginBottom: space.s3 },
  rangeBar: {
    height: 6,
    borderRadius: radius.pill,
    backgroundColor: color.surface3,
    justifyContent: 'center',
  },
  rangeDot: {
    position: 'absolute',
    width: 10,
    height: 10,
    borderRadius: 5,
    marginLeft: -5,
    backgroundColor: color.accent,
  },
  rangeEnds: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: space.s1,
  },
  evidence: { marginBottom: space.s2 },
  evHead: {
    flexDirection: 'row',
    paddingBottom: space.s1,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.line,
  },
  evRow: {
    flexDirection: 'row',
    paddingVertical: space.s1,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.line,
  },
  evMetric: { flex: 2 },
  evCol: { flex: 1, textAlign: 'right' },
  newsItem: {
    gap: 2,
    paddingVertical: space.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.line,
  },
});
