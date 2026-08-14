import { Redirect } from 'expo-router';

/**
 * Deep-link target for `cirvia://digest` (the morning-digest push).
 *
 * The Digest screen itself lives at `(tabs)/index`, and a route group is
 * transparent in a URL, so there is no `/digest` path for the link to resolve
 * to without this redirect.
 */
export default function DigestLink() {
  return <Redirect href="/(tabs)" />;
}
