import { useQuery } from '@tanstack/react-query';
import { Redirect } from 'expo-router';
import { View } from 'react-native';

import { api } from '@/api/client';
import type { PortfolioStatus } from '@/api/types';
import { useSession } from '@/auth/session';
import { color } from '@/theme/tokens';

/**
 * Entry gate.
 *
 * Onboarding is for users with no portfolio yet. An existing portfolio — even
 * behind a dead brokerage link — routes to the dashboard, which shows a
 * reconnect banner; sending them to onboarding would trap a fully set-up user
 * in a wizard they have already finished. Profile state deliberately plays no
 * part in this decision, for the same reason.
 *
 * On any error the dashboard wins: it degrades into empty states, whereas a
 * wrongly-shown wizard is a dead end.
 */
export default function Index() {
  const { session } = useSession();

  const status = useQuery<PortfolioStatus, Error>({
    queryKey: ['portfolio-status'],
    queryFn: () => api<PortfolioStatus>('/portfolio/status'),
    enabled: !!session,
    retry: false,
    staleTime: 60_000,
  });

  if (!session) return <Redirect href="/(auth)/sign-in" />;

  // Hold on the splash-coloured canvas rather than flashing the dashboard and
  // then bouncing into onboarding a moment later.
  if (status.isLoading) return <View style={{ flex: 1, backgroundColor: color.bg }} />;

  const settled = status.data?.connected || status.data?.has_positions;
  return <Redirect href={settled || status.isError ? '/(tabs)' : '/(onboarding)/profile'} />;
}
