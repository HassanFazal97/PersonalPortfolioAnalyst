import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { Stack } from 'expo-router';
import * as Notifications from 'expo-notifications';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { installOnlineManager } from '@/api/online';
import { persistOptions, queryClient } from '@/api/query';
import { SessionProvider, useSession } from '@/auth/session';
import { syncTokenIfEnabled } from '@/push/register';
import { usePushTaps } from '@/push/usePushTaps';
import { color } from '@/theme/tokens';

void SplashScreen.preventAutoHideAsync();

// Must run before the first query: without it TanStack assumes a browser and
// treats a dead connection as online.
installOnlineManager();

// A push that arrives while the app is open should still be seen — it is a
// pointer to something that just changed, not chatter.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

/** Holds the splash until the stored session has been read off the Keychain. */
function SplashGate() {
  const { ready } = useSession();
  usePushTaps();

  useEffect(() => {
    if (ready) void SplashScreen.hideAsync();
  }, [ready]);

  // The OS can rotate a push token at any time, and re-registering is also
  // what revives one Expo previously reported dead.
  useEffect(() => {
    if (ready) void syncTokenIfEnabled();
  }, [ready]);

  if (!ready) return null;
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="(onboarding)" />
      <Stack.Screen name="chat" options={{ presentation: 'modal' }} />
      <Stack.Screen name="push-priming" options={{ presentation: 'modal' }} />
      <Stack.Screen name="digest" />
      <Stack.Screen name="news" />
      <Stack.Screen name="stock/[ticker]" />
      <Stack.Screen name="picks" />
      <Stack.Screen name="dives/index" />
      <Stack.Screen name="dives/[id]" />
      <Stack.Screen name="settings/index" />
      <Stack.Screen name="settings/account" />
      <Stack.Screen name="settings/brokerage" />
      <Stack.Screen name="settings/delivery" />
      <Stack.Screen name="settings/plan" />
      <Stack.Screen name="settings/danger" />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: color.bg }}>
      <SafeAreaProvider>
        <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
          <SessionProvider>
            <StatusBar style="dark" />
            <SplashGate />
          </SessionProvider>
        </PersistQueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
