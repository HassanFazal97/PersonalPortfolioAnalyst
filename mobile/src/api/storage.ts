import { createMMKV, type MMKV } from 'react-native-mmkv';

/**
 * Two stores, deliberately separate.
 *
 * `cache` holds ETag'd response bodies and the TanStack Query dump — every
 * byte of it is server data for the signed-in user, so it is wiped wholesale
 * on sign-out. `prefs` holds device-local choices (last tab, dismissed
 * nudges) that survive an account switch.
 *
 * Neither holds credentials; the session lives in SecureStore.
 */
export const cache = createMMKV({ id: 'cirvia-cache' });
export const prefs = createMMKV({ id: 'cirvia-prefs' });

/** Called on sign-out and on a hard auth failure. */
export function clearAllCaches(): void {
  cache.clearAll();
  // Session-scoped nudges reset with the account; genuinely device-level
  // preferences would need to move to their own store to survive this.
  prefs.clearAll();
}

export function readJson<T>(store: MMKV, key: string): T | null {
  const raw = store.getString(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    store.remove(key);
    return null;
  }
}

export function writeJson(store: MMKV, key: string, value: unknown): void {
  try {
    store.set(key, JSON.stringify(value));
  } catch {
    // A cache write is never worth failing a render over.
  }
}
