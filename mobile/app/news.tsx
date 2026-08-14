import { Redirect } from 'expo-router';

/** Deep-link target for `cirvia://news` (macro and portfolio alerts). */
export default function NewsLink() {
  return <Redirect href="/(tabs)/news" />;
}
