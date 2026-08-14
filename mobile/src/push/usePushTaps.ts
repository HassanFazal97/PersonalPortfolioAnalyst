import * as Notifications from 'expo-notifications';
import { useRouter } from 'expo-router';
import { useEffect } from 'react';

import { APP_SCHEME } from '@/config';

/**
 * Route a notification tap to the screen it points at.
 *
 * The deep link lives in `data.deep_link`, set by the server's fan-out
 * (`enqueue_outbound(push=True, deep_link=…)`). Handled here rather than by
 * expo-router's own linking, because the URL arrives inside a notification
 * response, not as an app-open URL.
 */
export function usePushTaps(): void {
  const router = useRouter();

  useEffect(() => {
    const go = (response: Notifications.NotificationResponse | null) => {
      const link = response?.notification.request.content.data?.deep_link;
      if (typeof link !== 'string' || !link.startsWith(`${APP_SCHEME}://`)) return;
      const path = link.slice(`${APP_SCHEME}://`.length);
      if (!path) return;
      router.push(`/${path}` as never);
    };

    // A tap that launched the app cold: the response is waiting rather than
    // arriving through the listener.
    void Notifications.getLastNotificationResponseAsync().then(go);

    const sub = Notifications.addNotificationResponseReceivedListener(go);
    return () => sub.remove();
  }, [router]);
}
