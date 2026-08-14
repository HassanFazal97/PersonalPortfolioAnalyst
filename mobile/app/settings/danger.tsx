import { useState } from 'react';
import { Alert } from 'react-native';

import { api, ApiError } from '@/api/client';
import { useSession } from '@/auth/session';
import { Group, Row, SettingsScreen } from '@/settings/Section';
import { space } from '@/theme/tokens';
import { Button, ErrorNote, Field, Txt } from '@/ui';

/**
 * Account deletion, mandatory under Apple 5.1.1(v) and reachable in two taps
 * from the tab bar.
 *
 * On success the session is cleared and every local cache wiped — leftover
 * portfolio data after a delete is a legitimate store-review privacy finding.
 * The server tombstones the auth id so the JWT the caller is still holding
 * cannot silently re-provision a fresh empty account.
 */
export default function DangerScreen() {
  const { signOut } = useSession();
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const armed = confirmation.trim().toUpperCase() === 'DELETE';

  const remove = async () => {
    setError(null);
    setBusy(true);
    try {
      await api('/me', { method: 'DELETE' });
      // Clears the session and wipes MMKV.
      await signOut();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.detail
          : 'Could not delete your account. Try again in a minute.',
      );
      setBusy(false);
    }
  };

  const confirm = () =>
    Alert.alert(
      'Delete your account?',
      "You'll be signed out on every device, right now. This cannot be undone.",
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: () => void remove() },
      ],
    );

  return (
    <SettingsScreen title="Delete account">
      {error ? <ErrorNote message={error} /> : null}

      <Txt variant="bodySm" tone="ink2" style={styles.lead}>
        This permanently removes your account. It cannot be undone.
      </Txt>

      <Group label="What gets deleted">
        <Row label="Holdings and sync history" />
        <Row label="Every digest and deep dive report" />
        <Row label="Your investor profile and watchlist" />
        <Row label="Delivery details and registered devices" />
        <Row label="Your sign-in" />
      </Group>

      <Group label="Billing">
        <Row
          label="Your subscription is cancelled immediately"
          hint="You won't be charged again. There is no refund for the current period."
        />
      </Group>

      <Field
        label="Type DELETE to confirm"
        value={confirmation}
        onChangeText={setConfirmation}
        autoCapitalize="characters"
        autoCorrect={false}
        placeholder="DELETE"
      />

      <Button
        label="Delete my account"
        variant="danger"
        onPress={confirm}
        disabled={!armed}
        loading={busy}
      />
    </SettingsScreen>
  );
}

const styles = { lead: { marginBottom: space.s4 } } as const;
