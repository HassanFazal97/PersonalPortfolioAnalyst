import { Redirect, Stack } from 'expo-router';

import { useSession } from '@/auth/session';
import { OnboardingProvider } from '@/onboarding/state';

export default function OnboardingLayout() {
  const { session } = useSession();
  if (!session) return <Redirect href="/(auth)/sign-in" />;
  return (
    <OnboardingProvider>
      <Stack screenOptions={{ headerShown: false }} />
    </OnboardingProvider>
  );
}
