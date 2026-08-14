import { useRouter } from 'expo-router';
import { Alert, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ScrollView } from 'react-native';

import { useDashboard } from '@/api/bootstrap';
import { useSession } from '@/auth/session';
import { Group, Row } from '@/settings/Section';
import { color, space } from '@/theme/tokens';
import { Avatar, Txt } from '@/ui';

export default function SettingsIndex() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { signOut } = useSession();
  const { data } = useDashboard();

  const me = data?.sections.me.value;
  const status = data?.sections.status.value;
  const notifications = data?.sections.notifications.value;

  const planLabel = me?.trial.active
    ? 'Pro trial'
    : (me?.effective_plan ?? me?.plan) === 'pro'
      ? 'Pro'
      : 'Free';

  const channelLabel = notifications?.preferred_channel
    ? notifications.preferred_channel === 'sms'
      ? 'Text message'
      : notifications.preferred_channel === 'discord'
        ? 'Discord'
        : 'Email'
    : 'Not set up';

  const confirmSignOut = () =>
    Alert.alert('Sign out?', 'Your cached portfolio data is removed from this device.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign out', style: 'destructive', onPress: () => void signOut() },
    ]);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Txt variant="display" tone="ink">
          Settings
        </Txt>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <Group>
          <Row
            label={me?.email ?? 'Your account'}
            hint={planLabel}
            onPress={() => router.push('/settings/account')}
            right={<Avatar email={me?.email} size={30} />}
          />
        </Group>

        <Group>
          <Row
            label="Brokerage"
            value={
              status?.connected
                ? `${status.accounts_count} account${status.accounts_count === 1 ? '' : 's'}`
                : status?.has_positions
                  ? 'Manual holdings'
                  : 'Not connected'
            }
            onPress={() => router.push('/settings/brokerage')}
          />
          <Row
            label="Delivery"
            value={channelLabel}
            onPress={() => router.push('/settings/delivery')}
          />
          <Row
            label="Investor profile"
            value={me?.profile?.completed ? 'Set' : 'Not set'}
            onPress={() => router.push('/(onboarding)/profile?personalize=1')}
          />
          <Row label="Plan" value={planLabel} onPress={() => router.push('/settings/plan')} />
        </Group>

        <Group label="Analysis">
          <Row
            label="Model Picks"
            value={planLabel === 'Free' ? 'Pro' : undefined}
            onPress={() => router.push('/picks')}
          />
          <Row label="Deep dives" onPress={() => router.push('/dives')} />
        </Group>

        <Group label="More">
          {/* Risk Lab is deferred to v1.1: a pointer, not a purchase link. */}
          <Row label="Risk Lab" value="On cirvia.ca" />
          <Row label="Methodology" value="cirvia.ca/methodology" />
          <Row label="Terms & privacy" value="cirvia.ca/terms" />
        </Group>

        <Group>
          <Row label="Sign out" destructive onPress={confirmSignOut} />
          <Row
            label="Delete account"
            destructive
            onPress={() => router.push('/settings/danger')}
          />
        </Group>

        <Txt variant="caption" tone="ink3" center>
          Cirvia 1.0.0 · cirvia.ca
        </Txt>
        <Txt variant="caption" tone="ink3" center style={styles.disclaimer}>
          Informational only. Cirvia never gives buy or sell advice.
        </Txt>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  header: { paddingHorizontal: space.s4, paddingTop: space.s2, paddingBottom: space.s3 },
  content: { paddingHorizontal: space.s4, paddingBottom: space.s9 },
  disclaimer: { marginTop: space.s1 },
});
