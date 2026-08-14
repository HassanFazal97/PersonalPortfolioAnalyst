import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import { api } from '@/api/client';

/** Deep dives (`/deep-dive`) and Model Picks (`/stocks/picks`). */

export type DeepDiveReport = {
  report_id: string;
  run_id: string;
  status: 'running' | 'completed' | 'partial' | 'error' | string;
  progress: Record<string, unknown>;
  report: string | null;
  summary: string | null;
  cost_usd: number | null;
  created_at: string | null;
  completed_at: string | null;
};

export type PickFactor = Record<string, number | null>;

export type Pick = {
  ticker: string;
  name?: string | null;
  sector?: string | null;
  industry?: string | null;
  thesis?: string;
  why_now?: string | null;
  confidence?: number | null;
  demoted?: boolean;
  /** 'ok' when the analyst stage ran; anything else means quant scores only. */
  analysis?: string;
  factors?: PickFactor;
  risks?: { text: string; severity?: string }[];
  valuation_evidence?: {
    metric: string;
    value?: number | string | null;
    sector_median?: number | string | null;
  }[];
  verification?: {
    critic_ran?: boolean;
    checked?: number;
    verified?: number;
    challenged?: number;
  };
};

export type Mover = {
  ticker: string;
  change_pct?: number | null;
  sigma?: number | null;
  catalyst?: string | null;
  name?: string | null;
};

export type PicksPayload = {
  available: boolean;
  note?: string;
  status?: string;
  stale?: boolean;
  stale_note?: string;
  as_of?: string;
  headline?: string;
  overview?: string;
  picks?: Pick[];
  movers?: Mover[];
  disclaimer?: string;
  verification_summary?: {
    checked: number;
    verified: number;
    challenged: number;
    critic_ran: boolean;
  };
};

export function useDeepDives(): UseQueryResult<{ reports: DeepDiveReport[] }, Error> {
  return useQuery<{ reports: DeepDiveReport[] }, Error>({
    queryKey: ['deep-dives'],
    queryFn: () => api<{ reports: DeepDiveReport[] }>('/deep-dive'),
    staleTime: 60_000,
  });
}

export function useDeepDive(id: string): UseQueryResult<DeepDiveReport, Error> {
  return useQuery<DeepDiveReport, Error>({
    queryKey: ['deep-dive', id],
    queryFn: () => api<DeepDiveReport>(`/deep-dive/${id}`),
    // A running dive is polled rather than streamed here: the SSE tail is for
    // the screen that started it, while this one may be opened from a push
    // long after the run finished.
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 5_000 : false,
  });
}

export function useStartDeepDive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<{ report_id: string; run_id: string }>('/deep-dive', { method: 'POST' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['deep-dives'] });
    },
  });
}

export function usePicks(): UseQueryResult<PicksPayload, Error> {
  return useQuery<PicksPayload, Error>({
    queryKey: ['picks'],
    queryFn: () => api<PicksPayload>('/stocks/picks'),
    // Generated once globally per day; a 402 is the Pro gate, not a failure
    // worth retrying.
    staleTime: 15 * 60_000,
    retry: false,
  });
}
