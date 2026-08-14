import NetInfo from '@react-native-community/netinfo';
import { onlineManager } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

/**
 * Wire real connectivity into TanStack Query.
 *
 * Without this the default online manager assumes a browser and treats the
 * app as permanently online, so every query on a dead connection burns its
 * retries and lands on an error screen — even when a perfectly good cached
 * copy is sitting in MMKV. With it, queries pause instead and resume on
 * reconnect, and the stored bootstrap keeps rendering meanwhile.
 */
export function installOnlineManager(): void {
  onlineManager.setEventListener((setOnline) =>
    NetInfo.addEventListener((state) => {
      // `isInternetReachable` is null until the first probe finishes; treat
      // that as online rather than flashing an offline banner at launch.
      setOnline(Boolean(state.isConnected) && state.isInternetReachable !== false);
    }),
  );
}

/** For the offline banner. Mirrors what the query client is acting on. */
export function useIsOffline(): boolean {
  const [offline, setOffline] = useState(!onlineManager.isOnline());

  useEffect(() => {
    return onlineManager.subscribe((online) => setOffline(!online));
  }, []);

  return offline;
}
