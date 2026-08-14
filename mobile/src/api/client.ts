import { Platform } from 'react-native';

import { supabase } from '@/auth/supabase';
import { API_BASE } from '@/config';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/** Injected by `SessionProvider` so this module stays free of React state. */
let signOut: (() => Promise<void>) | null = null;

export function setSignOutHandler(handler: () => Promise<void>): void {
  signOut = handler;
}

/**
 * Single-flight token refresh.
 *
 * Every screen fires its own query on foreground, so an expired session would
 * otherwise start one refresh per in-flight request — and each returns a new
 * refresh token, invalidating the others. One promise, shared by all callers.
 */
let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = supabase.auth
      .refreshSession()
      .then(({ data, error }) => (error ? null : (data.session?.access_token ?? null)))
      .catch(() => null)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

async function currentAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

/**
 * A bearer token for a request this module doesn't make itself — the SSE
 * reader, which is XHR-based and sets its own headers. Refreshes first when
 * the stored token is close to expiry, because an EventSource that opens with
 * a stale token gets a 401 it cannot retry the way `authedFetch` can.
 */
export async function accessTokenForStream(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  const session = data.session;
  if (!session) return null;
  const expiresAt = session.expires_at ? session.expires_at * 1000 : 0;
  if (expiresAt && expiresAt - Date.now() < 60_000) {
    return (await refreshAccessToken()) ?? session.access_token;
  }
  return session.access_token;
}

export type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

/**
 * One authenticated request against the API.
 *
 * On a 401 the token is refreshed once and the request replayed. A second
 * 401 means the refresh token itself is dead — or the account was deleted and
 * tombstoned, which the server answers with 401 by design — so the only
 * correct move is to sign out rather than loop.
 */
export async function authedFetch(
  path: string,
  options: RequestOptions = {},
  retrying = false,
): Promise<Response> {
  const token = await currentAccessToken();
  const { method = 'GET', body, headers = {}, signal } = options;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    signal,
    headers: {
      Accept: 'application/json',
      'X-Client': `cirvia-mobile/${Platform.OS}`,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status !== 401 || retrying) return response;

  const fresh = await refreshAccessToken();
  if (!fresh) {
    await signOut?.();
    return response;
  }
  return authedFetch(path, options, true);
}

/** `authedFetch` plus JSON decoding and the server's `detail` on failure. */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await authedFetch(path, options);
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function toApiError(response: Response): Promise<ApiError> {
  let detail = `Request failed (${response.status})`;
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === 'string') detail = payload.detail;
  } catch {
    // Non-JSON error body (a proxy 502, say) — the status line is all we have.
  }
  return new ApiError(response.status, stripPurchaseCopy(detail));
}

/**
 * The server's 402 copy ends with an "Upgrade to Pro…" clause. Rendering that
 * inside the iOS app would be soliciting an out-of-app purchase, which is the
 * most common first-submission rejection. The rest of the message is the part
 * the user actually needs, so only the clause is removed.
 *
 * Android keeps the same code path in v1 deliberately: one behaviour to
 * reason about, and the storefront rules are moving in the same direction.
 */
export function stripPurchaseCopy(detail: string): string {
  return detail
    .replace(/\s*Upgrade to Pro[^.]*\.?/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}
