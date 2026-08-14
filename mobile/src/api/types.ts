/**
 * Payload shapes for `GET /dashboard/bootstrap`.
 *
 * Each section is byte-identical to the payload of its own endpoint — that is
 * a deliberate server-side property (`_build_section` in `app/main.py`), so
 * these types serve both the aggregated read and the individual routes.
 * Fields are optional where the server can legitimately omit them.
 */

export type Plan = 'free' | 'pro';

export type Trial = {
  active: boolean;
  ends_at: string | null;
  /** Trial lapsed and digests are paused until the user picks a plan. */
  decision_pending: boolean;
};

export type Billing = {
  enabled: boolean;
  annual_available: boolean;
  has_billing_account: boolean;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
};

export type Profile = {
  completed?: boolean;
  prompt_dismissed?: boolean;
  [key: string]: unknown;
};

export type ChatQuota = {
  used?: number;
  limit?: number | null;
  remaining?: number | null;
  [key: string]: unknown;
};

export type Me = {
  user_id: string;
  email: string | null;
  plan: Plan;
  effective_plan: Plan;
  timezone: string;
  digest_send_time: string;
  digest_enabled: boolean;
  preferred_channel: string | null;
  digest_tickers: string[];
  digest_tickers_limit: number | null;
  digest_tickers_editable: boolean;
  is_owner: boolean;
  profile: Profile;
  trial: Trial;
  billing: Billing;
  chat_quota: ChatQuota;
};

export type Position = {
  ticker: string;
  quantity: number;
  avg_cost: number;
  currency: string;
  account: string | null;
  last_price: number | null;
  day_change_pct: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  error?: string;
};

export type PortfolioTotals = {
  total_market_value_cad?: number;
  total_cost_basis_cad?: number;
  total_unrealized_pnl_cad?: number;
  total_unrealized_pnl_pct?: number | null;
  usdcad_rate?: number | null;
  includes_all_positions?: boolean;
};

export type Portfolio = {
  positions: Position[];
  totals: PortfolioTotals;
  note?: string;
};

export type Digest = {
  date: string;
  body: string;
  generated_at: string | null;
} | null;

export type NewsItem = {
  id?: number | string;
  kind?: string;
  title?: string;
  body?: string;
  url?: string | null;
  ticker?: string | null;
  severity?: string | null;
  category?: string | null;
  published_at?: string | null;
  created_at?: string | null;
};

export type News = { items: NewsItem[] };

export type WatchlistItem = {
  ticker: string;
  created_at: string | null;
  last_price: number | null;
  day_change_pct: number | null;
  /** True when the user also holds it — the web hides those from Watching. */
  held: boolean;
};

export type Watchlist = {
  items: WatchlistItem[];
  /** Plan cap, same limit/used/remaining shape as the chat quota. */
  limit?: number | null;
  used?: number;
  remaining?: number | null;
};

export type PortfolioStatus = {
  registered: boolean;
  connected: boolean;
  connection_disabled: boolean;
  accounts_count: number;
  has_positions: boolean;
  last_sync_at: string | null;
  last_sync_error: string | null;
};

export type NotificationChannel = {
  channel: string;
  destination_masked: string | null;
  verified: boolean;
  opted_out: boolean;
  consented: boolean;
};

export type PushDevice = {
  id: string;
  platform: string;
  kinds: string[];
  /** Masked token — the sendable value is never returned to a client. */
  masked: string;
  last_seen_at: string | null;
};

export type Notifications = {
  preferred_channel: string | null;
  /** Never includes 'push': it is a fan-out, not a selectable destination. */
  available_channels: string[];
  discord_oauth: boolean;
  channels: NotificationChannel[];
  devices: PushDevice[];
};

/** `SECTION_NAMES` in `app/perf/snapshot.py`, in the same order. */
export const SECTION_NAMES = [
  'me',
  'portfolio',
  'watchlist',
  'digest',
  'news',
  'status',
  'notifications',
] as const;

export type SectionName = (typeof SECTION_NAMES)[number];

export type SectionData = {
  me: Me;
  portfolio: Portfolio;
  watchlist: Watchlist;
  digest: Digest;
  news: News;
  status: PortfolioStatus;
  notifications: Notifications;
};

/** A section is either built data or the error string from building it. */
export type Section<T> = { data: T } | { error: string };

export type BootstrapPayload = {
  v: number;
  generated_at: string;
  /** Sections being rebuilt in the background right now. */
  refreshing: SectionName[];
  sections: { [K in SectionName]?: Section<SectionData[K]> };
};
