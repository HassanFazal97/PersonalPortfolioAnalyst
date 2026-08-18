import 'react-native-url-polyfill/auto';

/**
 * System-URL → route normalisation for the password-reset hand-off.
 *
 * The reset email points at https://…/app/auth/bridge with the Supabase
 * tokens in the URL fragment. On iOS the AASA file excludes /app/auth/*, so
 * the link opens in the browser and the bridge page bounces to
 * cirvia://reset?… — which expo-router routes natively. On Android the
 * App Links intent filter covers all of /app/*, so the same email link can
 * open the app directly, fragment and all; without this rewrite it would
 * dead-end on an unmatched /app/auth/bridge route. Both arrival shapes are
 * normalised here to /reset with the tokens as query params.
 */
export function redirectSystemPath({ path }: { path: string; initial: boolean }): string {
  try {
    const url = new URL(path);
    if (url.pathname === '/app/auth/bridge' || url.pathname === '/app/reset') {
      const params = new URLSearchParams(url.search);
      new URLSearchParams(url.hash.replace(/^#/, '')).forEach((v, k) => params.set(k, v));
      const qs = params.toString();
      return qs ? `/reset?${qs}` : '/reset';
    }
  } catch {
    // Not an absolute URL — leave it to expo-router's default handling.
  }
  return path;
}
