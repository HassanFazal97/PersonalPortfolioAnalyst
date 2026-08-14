import { pieColors, pieOther } from '@/theme/tokens';
import type { Portfolio, PortfolioTotals, Position } from '@/api/types';

/**
 * Portfolio maths, ported from the dashboard JS in `app/webapp.py`
 * (`mvCadOf`, the `byTicker` grouping, `renderSummary`, `renderHoldingsPie`).
 *
 * Pure functions on purpose: the metric strip, the holdings list, and the
 * donut all need the same grouped view, and three copies of this arithmetic
 * would disagree within a release.
 */

export type Holding = {
  ticker: string;
  quantity: number;
  currency: string;
  /** Number of accounts the ticker is held across (TFSA + RRSP counts as 2). */
  accounts: number;
  cost: number;
  marketValue: number | null;
  dayChangePct: number | null;
  totalReturnPct: number | null;
};

/** Market value in CAD, or null when it cannot be converted. */
export function mvCad(
  h: Pick<Holding, 'marketValue' | 'currency'>,
  totals: PortfolioTotals,
): number | null {
  if (h.marketValue == null) return null;
  if (h.currency === 'CAD') return h.marketValue;
  if (h.currency === 'USD' && totals.usdcad_rate != null) {
    return h.marketValue * totals.usdcad_rate;
  }
  return null;
}

/**
 * One row per ticker. The same instrument held in two accounts arrives as two
 * positions, and an ungrouped list reads as a duplicate-row bug.
 */
export function groupByTicker(positions: Position[]): Holding[] {
  const map = new Map<string, Holding>();

  for (const p of positions) {
    const existing = map.get(p.ticker);
    if (!existing) {
      map.set(p.ticker, {
        ticker: p.ticker,
        quantity: p.quantity,
        currency: p.currency,
        accounts: 1,
        cost: p.quantity * p.avg_cost,
        marketValue: p.market_value,
        dayChangePct: p.day_change_pct,
        totalReturnPct: p.unrealized_pnl_pct,
      });
      continue;
    }
    existing.accounts += 1;
    existing.quantity += p.quantity;
    existing.cost += p.quantity * p.avg_cost;
    if (p.market_value != null) {
      existing.marketValue = (existing.marketValue ?? 0) + p.market_value;
    }
    if (existing.dayChangePct == null) existing.dayChangePct = p.day_change_pct;
  }

  // Across accounts the stored per-position return no longer applies, so it is
  // re-derived cost-weighted.
  for (const h of map.values()) {
    if (h.accounts > 1 && h.marketValue != null && h.cost > 0) {
      h.totalReturnPct = (h.marketValue / h.cost - 1) * 100;
    }
  }

  return [...map.values()];
}

export type Summary = {
  value: number | null;
  includesAll: boolean;
  dayPnl: number | null;
  dayPct: number | null;
  totalPnl: number | null;
  totalPct: number | null;
};

/**
 * The three-up strip. There is no portfolio-level day change server-side, so
 * it is backed out of each priced holding: `value / (1 + pct)` recovers
 * yesterday's value, and the difference is the day's P&L.
 */
export function summarize(portfolio: Portfolio | null): Summary {
  const totals = portfolio?.totals ?? {};
  const empty: Summary = {
    value: null,
    includesAll: true,
    dayPnl: null,
    dayPct: null,
    totalPnl: null,
    totalPct: null,
  };
  if (!portfolio || totals.total_market_value_cad == null) return empty;

  let dayPnl: number | null = null;
  let covered = 0;
  for (const h of groupByTicker(portfolio.positions)) {
    const value = mvCad(h, totals);
    if (value == null || h.dayChangePct == null) continue;
    dayPnl = (dayPnl ?? 0) + value - value / (1 + h.dayChangePct / 100);
    covered += value;
  }

  return {
    value: totals.total_market_value_cad,
    includesAll: totals.includes_all_positions !== false,
    dayPnl,
    dayPct: dayPnl == null || !covered ? null : (dayPnl / (covered - dayPnl)) * 100,
    totalPnl: totals.total_unrealized_pnl_cad ?? null,
    totalPct: totals.total_unrealized_pnl_pct ?? null,
  };
}

export type Slice = {
  ticker: string;
  value: number;
  fraction: number;
  color: string;
  other: boolean;
};

const MAX_SLICES = 8;

/**
 * Donut slices, largest first, with everything past the eighth folded into
 * "Other". Colour is assigned by rank so a holding keeps the same hue here
 * that it has on the web.
 */
export function allocationSlices(
  positions: Position[],
  totals: PortfolioTotals,
): { slices: Slice[]; priced: number; excluded: number } {
  const priced = groupByTicker(positions)
    .map((h) => ({ ticker: h.ticker, value: mvCad(h, totals) }))
    .filter((s): s is { ticker: string; value: number } => s.value != null && s.value > 0)
    .sort((a, b) => b.value - a.value);

  const excluded = groupByTicker(positions).length - priced.length;
  const total = priced.reduce((sum, s) => sum + s.value, 0);
  if (!total) return { slices: [], priced: 0, excluded };

  const head = priced.slice(0, MAX_SLICES).map((s, i) => ({
    ticker: s.ticker,
    value: s.value,
    fraction: s.value / total,
    color: pieColors[i % pieColors.length] as string,
    other: false,
  }));

  if (priced.length > MAX_SLICES) {
    const rest = priced.slice(MAX_SLICES).reduce((sum, s) => sum + s.value, 0);
    head.push({
      ticker: 'Other',
      value: rest,
      fraction: rest / total,
      color: pieOther,
      other: true,
    });
  }

  return { slices: head, priced: priced.length, excluded };
}
