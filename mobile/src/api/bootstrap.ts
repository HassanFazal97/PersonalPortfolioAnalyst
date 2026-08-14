import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { conditionalGet, peekCached } from '@/api/etag';
import { cache, readJson, writeJson } from '@/api/storage';
import {
  SECTION_NAMES,
  type BootstrapPayload,
  type SectionData,
  type SectionName,
} from '@/api/types';

export const BOOTSTRAP_PATH = '/dashboard/bootstrap';
export const bootstrapKey = ['bootstrap'] as const;

/** One section, resolved: its value, whether it is refreshing, whether it failed. */
export type ResolvedSection<K extends SectionName> = {
  value: SectionData[K] | null;
  /** The server is rebuilding this section right now. */
  refreshing: boolean;
  /** Build failed this time. `value` may still hold the last good copy. */
  error: string | null;
  /** True when `value` came from a previous response rather than this one. */
  stale: boolean;
};

export type Dashboard = {
  generatedAt: string;
  sections: { [K in SectionName]: ResolvedSection<K> };
};

const LAST_GOOD = 'bootstrap:last-good';

type LastGood = Partial<{ [K in SectionName]: SectionData[K] }>;

/**
 * Fold a bootstrap payload into per-section values.
 *
 * The rule that matters: a section that comes back as `{error: …}` keeps the
 * value it had before. The server builds sections independently and a single
 * upstream hiccup (yfinance, SnapTrade) fails one of them — blanking a panel
 * that was working a second ago is worse than showing the last good copy with
 * an error note beside it.
 */
export function resolveSections(payload: BootstrapPayload): Dashboard {
  const lastGood = readJson<LastGood>(cache, LAST_GOOD) ?? {};
  const refreshing = new Set<SectionName>(payload.refreshing ?? []);

  // TypeScript cannot correlate the loop's key with its value type across an
  // indexed write, so the accumulator is loose and narrowed once on return.
  const out: Record<string, ResolvedSection<SectionName>> = {};

  for (const name of SECTION_NAMES) {
    const section = payload.sections?.[name];

    if (section && 'data' in section) {
      lastGood[name] = section.data as never;
      out[name] = {
        value: section.data,
        refreshing: refreshing.has(name),
        error: null,
        stale: false,
      };
      continue;
    }

    const previous = lastGood[name] ?? null;
    out[name] = {
      value: previous ?? null,
      refreshing: refreshing.has(name),
      error: section && 'error' in section ? section.error : null,
      stale: previous != null,
    };
  }

  writeJson(cache, LAST_GOOD, lastGood);
  return {
    generatedAt: payload.generated_at,
    sections: out as Dashboard['sections'],
  };
}

export async function fetchDashboard(signal?: AbortSignal): Promise<Dashboard> {
  const { data } = await conditionalGet<BootstrapPayload>(BOOTSTRAP_PATH, signal);
  return resolveSections(data);
}

/**
 * The dashboard's single read. Every tab renders from this one query, so a
 * tab switch costs nothing and a cold launch paints from MMKV before the
 * network settles.
 */
export function useDashboard(): UseQueryResult<Dashboard, Error> {
  return useQuery<Dashboard, Error>({
    queryKey: bootstrapKey,
    queryFn: ({ signal }) => fetchDashboard(signal),
    // The stored body is the placeholder, so the first frame after launch is
    // real content rather than a spinner. Revalidation still runs.
    placeholderData: () => {
      const cached = peekCached<BootstrapPayload>(BOOTSTRAP_PATH);
      return cached ? resolveSections(cached) : undefined;
    },
    staleTime: 30_000,
  });
}
