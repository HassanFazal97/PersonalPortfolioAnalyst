import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { api } from '@/api/client';
import { prefs } from '@/api/storage';

/**
 * Push registration.
 *
 * The OS permission prompt is a one-shot resource: once denied, it never
 * appears again and the user has to find the Settings app. So it is never
 * fired at launch — only after the priming screen, which itself only appears
 * after a successful first sync, when there is finally something worth
 * pushing about.
 */

const TOKEN_KEY = 'push:token';
const PRIMED_KEY = 'push:primed';

export type PushKind = 'digest' | 'alert' | 'deep_dive' | 'trial';

export const DEFAULT_KINDS: PushKind[] = ['digest', 'alert', 'deep_dive'];

/** Whether the priming screen has already been shown (answered either way). */
export function hasBeenPrimed(): boolean {
  return prefs.getBoolean(PRIMED_KEY) === true;
}

export function markPrimed(): void {
  prefs.set(PRIMED_KEY, true);
}

export function storedToken(): string | null {
  return prefs.getString(TOKEN_KEY) ?? null;
}

/**
 * Ask the OS, then register the token with the API.
 *
 * Returns null when permission is refused or the build cannot receive push
 * (a simulator has no APNs token). Callers treat null as "carry on without
 * push" — it is never an error the user needs to see.
 */
/**
 * True on a build made without the paid Apple entitlements (see
 * `app.config.js`). Push cannot work there, so the prompt is never shown.
 */
export function isFreeBuild(): boolean {
  return Constants.expoConfig?.extra?.freeBuild === true;
}

export async function enablePush(kinds: PushKind[] = DEFAULT_KINDS): Promise<string | null> {
  markPrimed();

  // A simulator has no APNs token, and a free build has no entitlement to get
  // one — in both cases asking would burn the one permission prompt iOS
  // gives us and get nothing back.
  if (isFreeBuild()) return null;
  if (!Device.isDevice) return null;

  const existing = await Notifications.getPermissionsAsync();
  let granted = existing.granted;
  if (!granted && existing.canAskAgain) {
    const asked = await Notifications.requestPermissionsAsync();
    granted = asked.granted;
  }
  if (!granted) return null;

  if (Platform.OS === 'android') {
    // Android needs a channel before anything can be delivered.
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Digest and alerts',
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;

  let token: string;
  try {
    const result = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
    token = result.data;
  } catch {
    // No APNs/FCM credentials in this build — nothing the user can fix.
    return null;
  }

  try {
    await api('/me/devices', {
      method: 'POST',
      body: { expo_token: token, platform: Platform.OS, kinds },
    });
    prefs.set(TOKEN_KEY, token);
    return token;
  } catch {
    // The token is worthless until the server has it, so don't cache it —
    // the next launch retries via syncTokenIfEnabled.
    return null;
  }
}

/**
 * Re-register on launch. The OS can rotate a token at any time, and
 * re-registering is also what revives one Expo previously reported dead.
 */
export async function syncTokenIfEnabled(): Promise<void> {
  if (!storedToken()) return;
  if (!Device.isDevice) return;
  const { granted } = await Notifications.getPermissionsAsync();
  if (!granted) return;
  await enablePush();
}

/** Sign-out and "turn push off": stop this device receiving anything. */
export async function disablePush(): Promise<void> {
  const token = storedToken();
  if (!token) return;
  try {
    await api('/me/devices', { method: 'DELETE', body: { expo_token: token } });
  } catch {
    // Best effort: the server also disables a token Expo rejects.
  }
  prefs.remove(TOKEN_KEY);
}
