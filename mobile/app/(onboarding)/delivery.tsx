import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ApiError } from '@/api/client';
import { useNotifications, useRegisterChannel, useVerifyChannel } from '@/api/onboarding';
import { useSession } from '@/auth/session';
import { useOnboardingDraft } from '@/onboarding/state';
import { Choice, Step } from '@/onboarding/Step';
import { color, radius, space } from '@/theme/tokens';
import { Button, ErrorNote, Field, Txt } from '@/ui';

type Channel = 'email' | 'sms';

/**
 * Step 7: where the digest lands.
 *
 * Discord is deliberately absent here. Connecting it is an OAuth round-trip
 * through the browser, which is a poor last step in a first-run flow — it
 * lives in settings instead, where the user is not mid-onboarding.
 */
export default function DeliveryStep() {
  const router = useRouter();
  const { session } = useSession();
  const { clear } = useOnboardingDraft();
  const notifications = useNotifications();
  const register = useRegisterChannel();
  const verify = useVerifyChannel();

  const [channel, setChannel] = useState<Channel>('email');
  const [destination, setDestination] = useState(session?.user.email ?? '');
  const [consent, setConsent] = useState(false);
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const finish = () => {
    clear();
    router.replace('/(tabs)');
  };

  const sendCode = async () => {
    setError(null);
    if (!destination.trim()) {
      setError(channel === 'email' ? 'Enter your email address.' : 'Enter your phone number.');
      return;
    }
    if (channel === 'sms' && !consent) {
      setError('Tick the consent box to receive automated texts.');
      return;
    }
    try {
      await register.mutateAsync({ channel, destination: destination.trim(), consent });
      setSent(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Could not send the code. Try again.');
    }
  };

  const confirm = async () => {
    setError(null);
    try {
      await verify.mutateAsync({ channel, code: code.trim() });
      finish();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'That code did not work. Try again.');
    }
  };

  const available = notifications.data?.available_channels ?? ['email'];

  return (
    <Step
      step={7}
      title="Where should it land?"
      blurb="Your digest reaches you before the market opens. You can change this any time in settings."
      onSkip={finish}
      skipLabel="Later"
      footer={
        sent ? (
          <>
            <Button label="Confirm" onPress={confirm} loading={verify.isPending} disabled={!code.trim()} />
            <Button label="Use a different destination" variant="link" onPress={() => setSent(false)} />
          </>
        ) : (
          <Button label="Send me a code" onPress={sendCode} loading={register.isPending} />
        )
      }
    >
      {error ? <ErrorNote message={error} /> : null}

      {sent ? (
        <>
          <Txt variant="bodySm" tone="ink2" style={styles.gap}>
            We sent a code to {destination.trim()}. Enter it below to confirm.
          </Txt>
          <Field
            label="Verification code"
            value={code}
            onChangeText={(t) => setCode(t.replace(/[^0-9]/g, ''))}
            keyboardType="number-pad"
            maxLength={8}
            autoFocus
          />
        </>
      ) : (
        <>
          <Choice
            label="Email"
            hint="Arrives as a formatted brief"
            selected={channel === 'email'}
            onPress={() => {
              setChannel('email');
              setDestination(session?.user.email ?? '');
            }}
          />
          {available.includes('sms') ? (
            <Choice
              label="Text message"
              hint="A short version, on your phone"
              selected={channel === 'sms'}
              onPress={() => {
                setChannel('sms');
                setDestination('');
              }}
            />
          ) : null}

          <View style={styles.gap}>
            <Field
              label={channel === 'email' ? 'Email address' : 'Phone number'}
              value={destination}
              onChangeText={setDestination}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType={channel === 'email' ? 'email-address' : 'phone-pad'}
              textContentType={channel === 'email' ? 'emailAddress' : 'telephoneNumber'}
              placeholder={channel === 'email' ? 'you@example.ca' : '+1 555 000 0000'}
            />
          </View>

          {channel === 'sms' ? (
            <Pressable
              onPress={() => setConsent(!consent)}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: consent }}
              style={styles.consent}
            >
              <View style={[styles.box, consent && styles.boxOn]}>
                {consent ? (
                  <Txt variant="caption" tone="inverse">
                    ✓
                  </Txt>
                ) : null}
              </View>
              <Txt variant="caption" tone="ink2" style={styles.consentText}>
                I agree to receive automated texts from Cirvia. Message and data rates may
                apply; reply STOP to opt out.
              </Txt>
            </Pressable>
          ) : null}
        </>
      )}
    </Step>
  );
}

const styles = StyleSheet.create({
  gap: { marginTop: space.s3 },
  consent: { flexDirection: 'row', gap: space.s2, alignItems: 'flex-start' },
  consentText: { flex: 1 },
  box: {
    width: 20,
    height: 20,
    borderRadius: radius.s - 2,
    borderWidth: 1.5,
    borderColor: color.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  boxOn: { backgroundColor: color.accent, borderColor: color.accent },
});
