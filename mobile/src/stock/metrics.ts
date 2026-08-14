import type { StockDetail } from '@/api/stocks';
import { EMPTY, fmtBig, fmtNum, fmtPct, fmtSignedPct } from '@/format';

/**
 * The metric cards on the stock detail screen, ported from `fillEquityCards`,
 * `fillEtfCards`, and `fillPriceAction` in `app/webapp.py`.
 *
 * Grading bands come across unchanged. They are deliberately generous — a
 * glance cue, not a verdict — and only metrics with a defensible universal
 * band get a colour at all; sector-relative ones (P/S, P/B, EV/EBITDA, gross
 * margin) stay neutral, because "high" for a utility is "low" for software.
 */

export type Tone = 'ink' | 'gain' | 'loss' | 'warn';
export type Row = { label: string; value: string; tone?: Tone };
export type Card = { title: string; rows: Row[] };

/**
 * `good` and `bad` are the thresholds nearest green and red; which direction
 * is better is inferred from their order.
 */
function grade(v: number | null | undefined, text: string, good: number, bad: number): Row['tone'] {
  if (v == null) return undefined;
  const higherIsBetter = good > bad;
  if (higherIsBetter) return v >= good ? 'gain' : v >= bad ? 'warn' : 'loss';
  return v <= good ? 'gain' : v <= bad ? 'warn' : 'loss';
}

/** P/E needs its own guard: negative means unprofitable, which the plain
 * lower-is-better scale would happily paint green. */
function gradePE(v: number | null | undefined): Row['tone'] {
  if (v == null) return undefined;
  if (v < 0) return 'loss';
  return grade(v, '', 20, 40);
}

const g = (o: Record<string, unknown> | null | undefined, k: string): number | null => {
  const value = o?.[k];
  return typeof value === 'number' ? value : null;
};

export function equityCards(d: StockDetail): Card[] {
  const v = d.valuation;
  const growth = d.growth;
  const p = d.profitability;
  const fh = d.financial_health;

  return [
    {
      title: 'Valuation',
      rows: [
        { label: 'P/E (trailing)', value: fmtNum(g(v, 'trailing_pe'), 1) },
        {
          label: 'P/E (forward)',
          value: fmtNum(g(v, 'forward_pe'), 1),
          tone: gradePE(g(v, 'forward_pe')),
        },
        { label: 'PEG', value: fmtNum(g(v, 'peg')), tone: grade(g(v, 'peg'), '', 1, 2) },
        { label: 'Price / sales', value: fmtNum(g(v, 'price_to_sales'), 1) },
        { label: 'Price / book', value: fmtNum(g(v, 'price_to_book'), 1) },
        { label: 'EV / EBITDA', value: fmtNum(g(v, 'ev_to_ebitda'), 1) },
        {
          label: 'Price / FCF',
          value: fmtNum(g(v, 'price_to_fcf'), 1),
          tone: grade(g(v, 'price_to_fcf'), '', 25, 50),
        },
      ],
    },
    {
      title: 'Growth & profitability',
      rows: [
        {
          label: 'Revenue growth',
          value: fmtPct(g(growth, 'revenue_growth_pct')),
          tone: grade(g(growth, 'revenue_growth_pct'), '', 10, 0),
        },
        {
          label: 'Earnings growth',
          value: fmtPct(g(growth, 'earnings_growth_pct')),
          tone: grade(g(growth, 'earnings_growth_pct'), '', 10, 0),
        },
        { label: 'Gross margin', value: fmtPct(g(p, 'gross_margin_pct')) },
        { label: 'Operating margin', value: fmtPct(g(p, 'operating_margin_pct')) },
        {
          label: 'Net margin',
          value: fmtPct(g(p, 'net_margin_pct')),
          tone: grade(g(p, 'net_margin_pct'), '', 15, 5),
        },
        {
          label: 'Return on equity',
          value: fmtPct(g(p, 'roe_pct')),
          tone: grade(g(p, 'roe_pct'), '', 15, 8),
        },
      ],
    },
    {
      title: 'Financial health',
      rows: [
        {
          label: 'Debt / equity',
          value: fmtNum(g(fh, 'debt_to_equity')),
          tone: grade(g(fh, 'debt_to_equity'), '', 1, 2),
        },
        {
          label: 'Current ratio',
          value: fmtNum(g(fh, 'current_ratio')),
          tone: grade(g(fh, 'current_ratio'), '', 1.5, 1),
        },
        { label: 'Market cap', value: fmtBig(g(d.profile, 'market_cap')) },
      ],
    },
  ];
}

export function etfCards(d: StockDetail): Card[] {
  const etf = (d.etf ?? {}) as Record<string, unknown>;
  const holdings = Array.isArray(etf.top_holdings)
    ? (etf.top_holdings as { symbol?: string; name?: string; weight_pct?: number }[])
    : [];
  return [
    {
      title: 'Fund',
      rows: [
        {
          label: 'Expense ratio',
          value: fmtPct(g(etf, 'expense_ratio_pct')),
          tone: grade(g(etf, 'expense_ratio_pct'), '', 0.2, 0.6),
        },
        { label: 'Assets', value: fmtBig(g(etf, 'total_assets')) },
        { label: 'Category', value: (etf.category as string) || EMPTY },
        { label: 'Fund family', value: (etf.fund_family as string) || EMPTY },
        { label: 'Distribution yield', value: fmtPct(g(d.dividends, 'dividend_yield_pct')) },
      ],
    },
    {
      title: 'Top holdings',
      rows: holdings.length
        ? holdings.map((h) => ({
            label: `${h.symbol ?? ''} ${h.name ?? ''}`.trim(),
            value: fmtPct(h.weight_pct ?? null),
          }))
        : [{ label: 'Holdings data unavailable', value: EMPTY }],
    },
  ];
}

export function priceActionRows(d: StockDetail): Row[] {
  const pa = d.price_action;
  const div = d.dividends;
  const price = d.quote.last_price;
  const target = pa?.analyst_target ?? null;

  const beta =
    pa?.beta == null
      ? EMPTY
      : `${fmtNum(pa.beta)}${pa.beta_source === 'computed' ? ' (est.)' : ''}`;

  const targetText =
    target == null || price == null
      ? fmtNum(target)
      : `${fmtNum(target)} (${fmtSignedPct((target / price - 1) * 100)})`;

  const rating = pa?.analyst_rating
    ? `${pa.analyst_rating.replaceAll('_', ' ')}${pa.analyst_count ? ` (${pa.analyst_count})` : ''}`
    : EMPTY;

  return [
    {
      label: 'Off 52-week high',
      value: fmtSignedPct(pa?.pct_from_52w_high ?? null),
      tone: pa?.pct_from_52w_high == null ? undefined : 'ink',
    },
    { label: 'Beta', value: beta },
    { label: '50-day average', value: fmtNum(pa?.avg_50d ?? null) },
    { label: '200-day average', value: fmtNum(pa?.avg_200d ?? null) },
    { label: 'Analyst target', value: targetText },
    { label: 'Analyst rating', value: rating },
    {
      label: 'Short % of float',
      value: fmtPct(pa?.short_pct_of_float ?? null),
      tone: grade(pa?.short_pct_of_float ?? null, '', 5, 15),
    },
    { label: 'Dividend yield', value: fmtPct(g(div, 'dividend_yield_pct')) },
    {
      label: 'Payout ratio',
      value: fmtPct(g(div, 'payout_ratio_pct')),
      tone: grade(g(div, 'payout_ratio_pct'), '', 60, 90),
    },
  ];
}
