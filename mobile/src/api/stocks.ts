import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import { api } from '@/api/client';
import { bootstrapKey } from '@/api/bootstrap';
import { invalidateCached } from '@/api/etag';
import { BOOTSTRAP_PATH } from '@/api/bootstrap';
import type { NewsItem } from '@/api/types';

/** `GET /stocks/{ticker}` — everything the detail screen needs but history and news. */

export type Verdict = {
  label: string;
  as_of: string | null;
  not_scored_reason: string | null;
  /** Free plan: the label shows, the peer-median numbers behind it do not. */
  evidence_gated: boolean;
  evidence: {
    sector_z: number | null;
    metrics_used: number | null;
    sector_comparison: 'industry' | 'sector' | 'market' | string | null;
    sector: string | null;
    industry: string | null;
    metrics: Record<string, { value?: number | string; sector_median?: number | string }> | null;
  } | null;
} | null;

export type StockDetail = {
  profile: {
    ticker: string;
    quote_type?: string | null;
    name?: string | null;
    sector?: string | null;
    industry?: string | null;
    [key: string]: unknown;
  };
  quote: { last_price: number | null; day_change_pct: number | null };
  valuation: Record<string, number | null> | null;
  verdict: Verdict;
  growth: Record<string, number | null> | null;
  profitability: Record<string, number | null> | null;
  financial_health: Record<string, number | null> | null;
  dividends: Record<string, number | string | null> | null;
  price_action: {
    low_52w?: number | null;
    high_52w?: number | null;
    pct_from_52w_high?: number | null;
    beta?: number | null;
    beta_source?: string | null;
    avg_50d?: number | null;
    avg_200d?: number | null;
    analyst_target?: number | null;
    analyst_rating?: string | null;
    analyst_count?: number | null;
    short_pct_of_float?: number | null;
  } | null;
  earnings: { next_earnings_date: string | null; ex_dividend_date: string | null };
  etf: Record<string, unknown> | null;
  position: {
    quantity: number;
    avg_cost: number | null;
    cost_basis: number;
    market_value: number | null;
    currency: string;
    unrealized_pnl: number | null;
    unrealized_pnl_pct: number | null;
    weight_pct: number | null;
    annual_dividend_income: number | null;
    accounts: { account: string | null; quantity: number; market_value: number | null }[];
  } | null;
  held: boolean;
  watching: boolean;
  fetched_at: string | null;
};

export type Bar = { date: string; close: number; open?: number; high?: number; low?: number };

export type History = { ohlcv: Bar[]; intraday?: boolean };

/**
 * Range options, in the days the history endpoint expects.
 *
 * `1` is the intraday path; everything else goes through
 * `market.get_price_history`, which rejects anything outside 5–365 days — so
 * there is deliberately no 5Y here. Same four ranges the web offers.
 */
export const RANGES = [
  { key: 1, label: '1D' },
  { key: 30, label: '1M' },
  { key: 182, label: '6M' },
  { key: 365, label: '1Y' },
] as const;

export type RangeKey = (typeof RANGES)[number]['key'];

export function useStockDetail(ticker: string): UseQueryResult<StockDetail, Error> {
  return useQuery<StockDetail, Error>({
    queryKey: ['stock', ticker],
    queryFn: () => api<StockDetail>(`/stocks/${encodeURIComponent(ticker)}`),
    staleTime: 60_000,
  });
}

export function useStockHistory(
  ticker: string,
  days: RangeKey,
): UseQueryResult<History, Error> {
  return useQuery<History, Error>({
    queryKey: ['stock-history', ticker, days],
    queryFn: () => api<History>(`/stocks/${encodeURIComponent(ticker)}/history?days=${days}`),
    // The 1D view re-fetches once a minute, matching the server's intraday
    // cache TTL; historical ranges are static by nature.
    refetchInterval: days === 1 ? 60_000 : false,
    staleTime: days === 1 ? 60_000 : 60 * 60_000,
  });
}

export function useStockNews(ticker: string): UseQueryResult<{ items: NewsItem[] }, Error> {
  return useQuery<{ items: NewsItem[] }, Error>({
    queryKey: ['stock-news', ticker],
    queryFn: () =>
      api<{ items: NewsItem[] }>(
        // All three kinds: articles tagged to this ticker, alerts naming it,
        // and digests whose text mentions it.
        `/news?ticker=${encodeURIComponent(ticker)}&kind=digest,holding,alert`,
      ),
    staleTime: 5 * 60_000,
  });
}

/** Watch / unwatch. The watchlist also drives digest coverage, so the
 * dashboard's cached bootstrap has to be dropped, not just refetched. */
export function useWatchToggle(ticker: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (watching: boolean) => {
      await api(`/watchlist/${encodeURIComponent(ticker)}`, {
        method: watching ? 'DELETE' : 'POST',
      });
      return !watching;
    },
    onSuccess: (nowWatching) => {
      queryClient.setQueryData<StockDetail>(['stock', ticker], (prev) =>
        prev ? { ...prev, watching: nowWatching } : prev,
      );
      invalidateCached(BOOTSTRAP_PATH);
      void queryClient.invalidateQueries({ queryKey: bootstrapKey });
    },
  });
}
