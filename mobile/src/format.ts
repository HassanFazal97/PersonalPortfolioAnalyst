/**
 * Number and date formatting, ported from the helpers in `app/webapp.py`
 * (`fmtNum`, `fmtPct`, `pctSpan`, `fmtCur`, `fmtBig`, `newsDayLabel`).
 *
 * The em dash the web renders for a missing value is a real en dash here
 * (`–`), same as the HTML `&ndash;` it came from.
 */

export const EMPTY = '–';

export function fmtNum(v: number | null | undefined, dp = 2): string {
  return v == null ? EMPTY : v.toFixed(dp);
}

export function fmtPct(v: number | null | undefined, dp = 2): string {
  return v == null ? EMPTY : `${v.toFixed(dp)}%`;
}

/** Percent with an explicit sign, for day/total change. */
export function fmtSignedPct(v: number | null | undefined, dp = 2): string {
  if (v == null) return EMPTY;
  return `${v >= 0 ? '+' : ''}${v.toFixed(dp)}%`;
}

export function fmtCur(v: number | null | undefined, currency = 'CAD'): string {
  if (v == null) return EMPTY;
  try {
    return v.toLocaleString('en-CA', {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    });
  } catch {
    return v.toFixed(2);
  }
}

/** Whole-dollar form for the metric strip, where the cents are noise. */
export function fmtCurCompact(v: number | null | undefined, currency = 'CAD'): string {
  if (v == null) return EMPTY;
  try {
    return v.toLocaleString('en-CA', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    });
  } catch {
    return v.toFixed(0);
  }
}

export function fmtBig(v: number | null | undefined): string {
  if (v == null) return EMPTY;
  const a = Math.abs(v);
  if (a >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  return v.toLocaleString('en-CA');
}

/** Signed dollar delta, e.g. `−$318`. */
export function fmtSignedCur(v: number | null | undefined, currency = 'CAD'): string {
  if (v == null) return EMPTY;
  const body = fmtCurCompact(Math.abs(v), currency);
  return `${v < 0 ? '−' : '+'}${body}`;
}

/**
 * Day bucket label for the news feed. Uses the item's publish time when known
 * and its insertion time otherwise — the same fallback the web feed uses,
 * because holding articles carry `published_at` and digests do not.
 */
export function dayLabel(iso: string | null | undefined): string {
  if (!iso) return 'Earlier';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Earlier';
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === now.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Short clock time, for "updated at" strips. */
export function timeLabel(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

/**
 * Digest bodies are labelled plain-text sections. The web bolds the labels
 * with a regex over escaped HTML; here the same regex splits the body into
 * runs so the renderer can bold them without an HTML parser.
 *
 * Kept character-identical to `formatNewsBody` in `app/webapp.py` — if a new
 * label is added to the digest prompt, both copies need it.
 */
const LABELS = /^(PORTFOLIO:|TOP RISK|NOTABLE|WATCH TODAY:|HOLDINGS|WATCHLIST|QUIET:)/;

export type DigestRun = { text: string; label: boolean };

export function digestRuns(body: string): DigestRun[][] {
  return body.split('\n').map((rawLine) => {
    const match = rawLine.match(LABELS);
    if (!match) return [{ text: rawLine, label: false }];
    const head = match[1] ?? '';
    return [
      { text: head, label: true },
      { text: rawLine.slice(head.length), label: false },
    ];
  });
}
