import { useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useState } from 'react';

import { api, ApiError } from '@/api/client';
import { useNotifications, useRegisterChannel, useVerifyChannel } from '@/api/onboarding';
import { Group, Row, SettingsScreen } from '@/settings/Section';
import { space } from '@/theme/tokens';
import { Button, ErrorNote, Field, Tag, Txt } from '@/ui';

const LABELS: Record<string, string> = {
  email: 'Email',
  sms: 'Text message',
  discord: 'Discord',
};

export default function DeliveryScreen() {
  // Set when the Discord callback bounces back into the app.
  const { discord } = useLocalSearchParams<{ discord?: string }>();

  const notifications = useNotifications();
  const register = useRegisterChannel();
  const verify = useVerifyChannel();

  const [adding, setAdding] = useState<string | null>(null);
  const [destination, setDestination] = useState('');
  const [consent, setConsent] = useState(false);
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const data = notifications.data;
  const channels = data?.channels ?? [];
  const available = data?.available_channels ?? [];
  const devices = data?.devices ?? [];
  const kinds: string[] = devices[0]?.kinds ?? [];

  const toggleKind = async (kind: string) => {
    setError(null);
    const next = kinds.includes(kind)
      ? kinds.filter((k) => k !== kind)
      : [...kinds, kind];
    try {
      await api('/me/devices/kinds', { method: 'PATCH', body: { kinds: next } });
      await notifications.refetch();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Could not update notifications.');
    }
  };

  const setPreferred = async (channel: string) => {
    setError(null);
    try {
      await api('/me/notifications/preferred', { method: 'POST', body: { channel } });
      await notifications.refetch();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Could not switch channels.');
    }
  };

  const connectDiscord = async () => {
    setError(null);
    setBusy(true);
    try {
      // `return_to=app` makes the callback redirect to cirvia://settings/delivery,
      // which is what closes the auth session and hands control back here.
      const { url } = await api<{ url: string }>(
        '/me/notifications/discord/connect-url?return_to=app',
      );
      await WebBrowser.openAuthSessionAsync(url, 'cirvia://settings/delivery');
      await notifications.refetch();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.detail
          : 'Could not start the Discord connection. Try again.',
      );
    } finally {
      setBusy(false);
    }
  };

  const sendCode = async () => {
    setError(null);
    if (!destination.trim()) {
      setError('Enter a destination first.');
      return;
    }
    if (adding === 'sms' && !consent) {
      setError('Tick the consent box to receive automated texts.');
      return;
    }
    try {
      await register.mutateAsync({
        channel: adding!,
        destination: destination.trim(),
        consent,
      });
      setSent(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Could not send the code.');
    }
  };

  const confirmCode = async () => {
    setError(null);
    try {
      await verify.mutateAsync({ channel: adding!, code: code.trim() });
      setAdding(null);
      setSent(false);
      setCode('');
      setDestination('');
      await notifications.refetch();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'That code did not work.');
    }
  };

  return (
    <SettingsScreen title="Delivery">
      {discord === 'connected' ? (
        <Txt variant="bodySm" tone="accent" style={styles.note}>
          Discord connected. Your digest will arrive in the channel you picked.
        </Txt>
      ) : null}
      {discord === 'cancelled' ? (
        <Txt variant="caption" tone="ink3" style={styles.note}>
          Discord connection cancelled.
        </Txt>
      ) : null}
      {error ? <ErrorNote message={error} /> : null}

      <Group label="Where your digest goes">
        {channels.length ? (
          channels.map((c) => (
            <Row
              key={c.channel}
              label={LABELS[c.channel] ?? c.channel}
              hint={c.destination_masked ?? undefined}
              value={c.channel === data?.preferred_channel ? 'Preferred' : undefined}
              right={
                c.verified ? (
                  c.channel === data?.preferred_channel ? undefined : (
                    <Button
                      label="Use this"
                      variant="link"
                      onPress={() => void setPreferred(c.channel)}
                    />
                  )
                ) : (
                  <Tag label="Unverified" tone="warn" />
                )
              }
            />
          ))
        ) : (
          <Row label="Nothing set up yet" hint="Your digest only appears in the app." />
        )}
      </Group>

      {adding ? (
        <Group label={`Add ${LABELS[adding] ?? adding}`}>
          <Row label={sent ? 'Enter the code we sent' : 'Where should it go?'} />
        </Group>
      ) : null}

      {adding && !sent ? (
        <>
          <Field
            label={adding === 'sms' ? 'Phone number' : 'Email address'}
            value={destination}
            onChangeText={setDestination}
            autoCapitalize="none"
            keyboardType={adding === 'sms' ? 'phone-pad' : 'email-address'}
          />
          {adding === 'sms' ? (
            <Row
              label="I agree to receive automated texts"
              hint="Message and data rates may apply; reply STOP to opt out."
              value={consent ? 'Yes' : 'Tap to agree'}
              onPress={() => setConsent(!consent)}
            />
          ) : null}
          <Button label="Send me a code" onPress={sendCode} loading={register.isPending} />
          <Button label="Cancel" variant="link" onPress={() => setAdding(null)} />
        </>
      ) : null}

      {adding && sent ? (
        <>
          <Field
            label="Verification code"
            value={code}
            onChangeText={(t) => setCode(t.replace(/[^0-9]/g, ''))}
            keyboardType="number-pad"
            maxLength={8}
            autoFocus
          />
          <Button label="Confirm" onPress={confirmCode} loading={verify.isPending} />
          <Button label="Start over" variant="link" onPress={() => setSent(false)} />
        </>
      ) : null}

      {!adding && devices.length ? (
        <Group label="Push notifications">
          {(
            [
              ['digest', 'Morning digest'],
              ['alert', 'Unusual moves'],
              ['deep_dive', 'Deep dive ready'],
            ] as const
          ).map(([kind, label]) => (
            <Row
              key={kind}
              label={label}
              value={kinds.includes(kind) ? 'On' : 'Off'}
              onPress={() => void toggleKind(kind)}
            />
          ))}
          <Row
            label="This device"
            hint="Push rides alongside your digest channel, never instead of it."
            value={devices[0]?.masked}
          />
        </Group>
      ) : null}

      {!adding ? (
        <Group label="Add a channel">
          {available.includes('email') ? (
            <Row label="Email" onPress={() => setAdding('email')} />
          ) : null}
          {available.includes('sms') ? (
            <Row label="Text message" onPress={() => setAdding('sms')} />
          ) : null}
          {available.includes('discord') && data?.discord_oauth ? (
            <Row
              label="Discord"
              hint="Opens Discord to pick a server and channel"
              onPress={() => void connectDiscord()}
              right={busy ? <Txt variant="caption" tone="ink3">Opening…</Txt> : undefined}
            />
          ) : null}
        </Group>
      ) : null}

      <Txt variant="caption" tone="ink3" style={styles.note}>
        Your digest goes to one channel at a time. Changing it here changes it everywhere.
      </Txt>
    </SettingsScreen>
  );
}

const styles = { note: { marginTop: space.s3 } } as const;
