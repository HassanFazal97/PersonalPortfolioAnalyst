import { QueryClient } from '@tanstack/react-query';
import type { PersistedClient, Persister } from '@tanstack/react-query-persist-client';

import { ApiError } from '@/api/client';
import { cache, readJson, writeJson } from '@/api/storage';

const PERSIST_KEY = 'query-client';

/** MMKV persister. Synchronous storage, so the restore lands before first paint. */
export const mmkvPersister: Persister = {
  persistClient: async (client) => {
    writeJson(cache, PERSIST_KEY, client);
  },
  restoreClient: async () => readJson<PersistedClient>(cache, PERSIST_KEY) ?? undefined,
  removeClient: async () => {
    cache.remove(PERSIST_KEY);
  },
};

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Long enough that a foreground/background bounce doesn't refetch
      // everything, short enough that a day-old cache never renders as fresh.
      gcTime: 1000 * 60 * 60 * 24,
      staleTime: 1000 * 30,
      retry: (failureCount, error) => {
        // 401 is handled by the client (refresh, then sign out) and 4xx will
        // not fix itself on a retry; only transport and 5xx errors get one.
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 2;
      },
      refetchOnReconnect: true,
    },
  },
});

export const persistOptions = {
  persister: mmkvPersister,
  maxAge: 1000 * 60 * 60 * 24,
  // Bump when a cached shape changes so stale dumps are discarded rather than
  // rendered against new code.
  buster: 'v1',
} as const;
