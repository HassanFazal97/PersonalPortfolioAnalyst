import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import { BOOTSTRAP_PATH, bootstrapKey } from '@/api/bootstrap';
import { api } from '@/api/client';
import { invalidateCached } from '@/api/etag';
import type { Me, Notifications, PortfolioStatus } from '@/api/types';

/** Enum values mirrored from `app/profile.py`. Free text never reaches a prompt. */
export const HORIZONS = [
  { key: 'days', label: 'Days', hint: 'I trade around the news' },
  { key: 'weeks_months', label: 'Weeks to months', hint: 'I hold through a cycle' },
  { key: 'years', label: 'Years', hint: 'I buy and hold' },
  { key: 'decade_plus', label: 'A decade or more', hint: 'I am investing for later life' },
] as const;

export const EXPERIENCE_LEVELS = [
  { key: 'new', label: 'Just starting' },
  { key: 'lt_1y', label: 'Under a year' },
  { key: '1_5y', label: '1 to 5 years' },
  { key: '5_10y', label: '5 to 10 years' },
  { key: '10y_plus', label: 'Over 10 years' },
] as const;

export const GOALS = [
  { key: 'grow_long_term', label: 'Grow my money long term' },
  { key: 'income', label: 'Generate income' },
  { key: 'preserve_capital', label: 'Preserve what I have' },
  { key: 'short_term_gains', label: 'Short-term gains' },
  { key: 'retirement', label: 'Retirement' },
  { key: 'big_purchase', label: 'A big purchase' },
] as const;

export const POSTURES = [
  { key: 'defensive', label: 'A smoother ride' },
  { key: 'current', label: 'Your current mix' },
  { key: 'aggressive', label: 'Higher octane' },
] as const;

export type PostureKey = (typeof POSTURES)[number]['key'];

export type PostureBlock = {
  annualized_vol_pct: number;
  probability_of_loss_pct: number;
  horizon_days: number;
  simulations: number;
  bands_pct: Record<string, number[]>;
  terminal_pct: { p5: number; p50: number; p95: number };
  /** Absent when the book isn't analyzable yet and the fans are illustrative. */
  terminal_cad?: { p5: number; p50: number; p95: number };
};

export type Projections = {
  available: boolean;
  fallback: boolean;
  note?: string;
  portfolio_value_cad?: number;
  holdings_analyzed?: number;
  postures: Record<string, PostureBlock>;
  notes?: string[];
};

export type ProfileDraft = {
  experience?: string;
  horizon?: string;
  goals: string[];
  chosen_posture?: PostureKey;
};

export function useBrokerageStatus(enabled = true): UseQueryResult<PortfolioStatus, Error> {
  return useQuery<PortfolioStatus, Error>({
    queryKey: ['portfolio-status'],
    queryFn: () => api<PortfolioStatus>('/portfolio/status'),
    enabled,
    staleTime: 0,
  });
}

export function useProjections(): UseQueryResult<Projections, Error> {
  return useQuery<Projections, Error>({
    queryKey: ['risk-projections'],
    queryFn: () => api<Projections>('/me/profile/projections'),
    staleTime: 5 * 60_000,
  });
}

export function useNotifications(): UseQueryResult<Notifications, Error> {
  return useQuery<Notifications, Error>({
    queryKey: ['notifications'],
    queryFn: () => api<Notifications>('/me/notifications'),
    staleTime: 30_000,
  });
}

/**
 * Anything that changes server-side dashboard state has to drop the stored
 * bootstrap body as well as the query cache — the ETag layer would otherwise
 * revalidate against an ETag the server no longer considers current and the
 * dashboard would render yesterday's answer.
 */
function useDashboardInvalidator() {
  const queryClient = useQueryClient();
  return () => {
    invalidateCached(BOOTSTRAP_PATH);
    void queryClient.invalidateQueries({ queryKey: bootstrapKey });
  };
}

export function useSaveProfile() {
  const invalidate = useDashboardInvalidator();
  return useMutation({
    mutationFn: (draft: ProfileDraft) =>
      api<Me>('/me/profile', {
        method: 'PUT',
        body: {
          experience: draft.experience ?? null,
          horizon: draft.horizon ?? null,
          goals: draft.goals,
          chosen_posture: draft.chosen_posture ?? null,
        },
      }),
    onSuccess: invalidate,
  });
}

export function useSavePreferences() {
  const invalidate = useDashboardInvalidator();
  return useMutation({
    mutationFn: (body: {
      digest_send_time?: string;
      digest_enabled?: boolean;
      digest_tickers?: string[];
      timezone?: string;
    }) => api<Me>('/me', { method: 'PATCH', body }),
    onSuccess: invalidate,
  });
}

export function useSyncPortfolio() {
  const invalidate = useDashboardInvalidator();
  return useMutation({
    mutationFn: () => api<Record<string, unknown>>('/portfolio/sync', { method: 'POST' }),
    onSuccess: invalidate,
  });
}

export function useManualPortfolio() {
  const invalidate = useDashboardInvalidator();
  return useMutation({
    mutationFn: (positions: { ticker: string; quantity: number }[]) =>
      api<Record<string, unknown>>('/portfolio/manual', {
        method: 'POST',
        body: { positions },
      }),
    onSuccess: invalidate,
  });
}

export function useRegisterChannel() {
  return useMutation({
    mutationFn: (body: { channel: string; destination: string; consent: boolean }) =>
      api<{ status: string; channel: string }>('/me/notifications/channel', {
        method: 'POST',
        body,
      }),
  });
}

export function useVerifyChannel() {
  const invalidate = useDashboardInvalidator();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { channel: string; code: string }) =>
      api<Notifications>('/me/notifications/verify', { method: 'POST', body }),
    onSuccess: () => {
      invalidate();
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

/** The hosted SnapTrade portal URL. Never fetched until the user asks for it. */
export async function fetchConnectUrl(): Promise<string> {
  // Registration is idempotent and must precede the portal call for a user
  // who has never linked anything.
  await api('/portfolio/snaptrade/register', { method: 'POST' });
  const { url } = await api<{ url: string }>('/portfolio/connect-url');
  return url;
}
