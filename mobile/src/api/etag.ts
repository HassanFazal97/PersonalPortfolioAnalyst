import { authedFetch, toApiError } from '@/api/client';
import { cache, readJson, writeJson } from '@/api/storage';

/**
 * Conditional GET over MMKV.
 *
 * React Native's `fetch` has no HTTP cache, so `If-None-Match` has to be
 * driven by hand. The bootstrap endpoint is built for exactly this: its ETag
 * covers the sections only (not `generated_at`), so a warm revalidation is a
 * 304 with an empty body and the stored copy is reused verbatim.
 */

type CacheEntry<T> = { etag: string | null; body: T; storedAt: number };

const KEY = (path: string) => `etag:${path}`;

export type ConditionalResult<T> = {
  data: T;
  /** True when the server answered 304 and this came from MMKV. */
  notModified: boolean;
};

/** The last stored body for a path, without touching the network. */
export function peekCached<T>(path: string): T | null {
  return readJson<CacheEntry<T>>(cache, KEY(path))?.body ?? null;
}

export async function conditionalGet<T>(
  path: string,
  signal?: AbortSignal,
): Promise<ConditionalResult<T>> {
  const stored = readJson<CacheEntry<T>>(cache, KEY(path));

  const response = await authedFetch(path, {
    signal,
    headers: stored?.etag ? { 'If-None-Match': stored.etag } : {},
  });

  if (response.status === 304) {
    if (stored) return { data: stored.body, notModified: true };
    // The server matched an ETag we no longer hold (cache cleared mid-flight).
    // Re-ask unconditionally rather than returning nothing.
    cache.remove(KEY(path));
    return conditionalGet<T>(path, signal);
  }

  if (!response.ok) {
    // A cached copy is better than an error screen for a GET that succeeded
    // before — the caller decides whether to surface staleness.
    if (stored) return { data: stored.body, notModified: true };
    throw await toApiError(response);
  }

  const body = (await response.json()) as T;
  writeJson(cache, KEY(path), {
    etag: response.headers.get('etag'),
    body,
    storedAt: Date.now(),
  } satisfies CacheEntry<T>);

  return { data: body, notModified: false };
}

/** Drop one path's cached body — used after a write that invalidates it. */
export function invalidateCached(path: string): void {
  cache.remove(KEY(path));
}
