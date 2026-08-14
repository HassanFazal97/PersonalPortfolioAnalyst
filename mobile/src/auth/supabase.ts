import 'react-native-url-polyfill/auto';

import { createClient, type SupportedStorage } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';
import { AppState, type AppStateStatus } from 'react-native';

import { SUPABASE_ANON_KEY, SUPABASE_URL } from '@/config';

/**
 * The session holds a refresh token, so it goes in the Keychain / Android
 * Keystore rather than MMKV or AsyncStorage. Leaving a long-lived credential
 * in plain app storage is a legitimate store-review finding, not a nicety.
 *
 * SecureStore rejects keys with characters outside [A-Za-z0-9._-], and
 * supabase-js composes its key from the project ref, so it is sanitised here.
 */
const secureStorage: SupportedStorage = {
  getItem: (key) => SecureStore.getItemAsync(safeKey(key)),
  setItem: (key, value) => SecureStore.setItemAsync(safeKey(key), value),
  removeItem: (key) => SecureStore.deleteItemAsync(safeKey(key)),
};

function safeKey(key: string): string {
  return key.replace(/[^A-Za-z0-9._-]/g, '_');
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: secureStorage,
    autoRefreshToken: true,
    persistSession: true,
    // No URL to parse on native: recovery and confirm links are handled
    // explicitly by the deep-link handler, not by reading location.hash.
    detectSessionInUrl: false,
  },
});

/**
 * supabase-js schedules its refresh timer on an interval that a suspended app
 * does not run. Tying it to foreground/background means a session that expired
 * while the app was closed refreshes on the way back in, rather than surfacing
 * as a 401 on the first request.
 */
let subscribed = false;

export function startSessionAutoRefresh(): () => void {
  if (subscribed) return () => {};
  subscribed = true;

  const onChange = (state: AppStateStatus) => {
    if (state === 'active') {
      void supabase.auth.startAutoRefresh();
    } else {
      void supabase.auth.stopAutoRefresh();
    }
  };

  onChange(AppState.currentState);
  const sub = AppState.addEventListener('change', onChange);

  return () => {
    sub.remove();
    subscribed = false;
    void supabase.auth.stopAutoRefresh();
  };
}
