import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { supabase } from '@/auth/supabase';
import { color, space } from '@/theme/tokens';
import { Button, Txt, Field } from '@/ui';

type LinkState = 'checking' | 'ready' | 'invalid';

/**
 * Set a new password after a recovery deep link (cirvia://reset?…).
 *
 * Deliberately outside the (auth) group: claiming the recovery tokens
 * creates a session, and (auth)/_layout redirects any session to the tabs —
 * which would yank the user off this screen before they typed a password.
 */
export default function Reset() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{
    access_token?: string;
    refresh_token?: string;
    code?: string;
    error?: string;
  }>();

  const [linkState, setLinkState] = useState<LinkState>('checking');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const claim = async () => {
      try {
        if (params.error) throw new Error(params.error);
        if (typeof params.code === 'string' && params.code) {
          const { error: e } = await supabase.auth.exchangeCodeForSession(params.code);
          if (e) throw e;
        } else if (
          typeof params.access_token === 'string' &&
          typeof params.refresh_token === 'string'
        ) {
          const { error: e } = await supabase.auth.setSession({
            access_token: params.access_token,
            refresh_token: params.refresh_token,
          });
          if (e) throw e;
        } else {
          // No tokens in the link: an already-signed-in user may still set a
          // new password here; anyone else has a dead link.
          const { data } = await supabase.auth.getSession();
          if (!data.session) throw new Error('no session');
        }
        if (active) setLinkState('ready');
      } catch {
        if (active) setLinkState('invalid');
      }
    };
    void claim();
    return () => {
      active = false;
    };
    // Params are fixed for the life of this screen: it is only reached via a
    // fresh deep link, so the claim runs once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async () => {
    setError(null);
    if (password.length < 8) {
      setError('Use at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      const { error: e } = await supabase.auth.updateUser({ password });
      if (e) throw e;
      router.replace('/');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update your password. Try again.');
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={[styles.content, { paddingTop: insets.top + space.s9 }]}
        keyboardShouldPersistTaps="handled"
      >
        <Txt variant="display" tone="ink" style={styles.wordmark}>
          Cirvia
        </Txt>

        {linkState === 'checking' ? (
          <Txt variant="body" tone="ink2" style={styles.lead}>
            Checking your reset link…
          </Txt>
        ) : null}

        {linkState === 'invalid' ? (
          <>
            <Txt variant="body" tone="ink2" style={styles.lead}>
              This reset link is invalid or has expired. Request a new one from the sign-in
              screen.
            </Txt>
            <Button label="Back to sign in" onPress={() => router.replace('/')} />
          </>
        ) : null}

        {linkState === 'ready' ? (
          <>
            <Txt variant="body" tone="ink2" style={styles.lead}>
              Choose a new password for your account. At least 8 characters.
            </Txt>
            <Field
              label="New password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoCapitalize="none"
              autoComplete="new-password"
              textContentType="newPassword"
              returnKeyType="next"
            />
            <Field
              label="Confirm new password"
              value={confirm}
              onChangeText={setConfirm}
              secureTextEntry
              autoCapitalize="none"
              autoComplete="new-password"
              textContentType="newPassword"
              returnKeyType="go"
              onSubmitEditing={submit}
              error={error}
            />
            <Button label="Set new password" onPress={submit} loading={busy} />
            <View style={styles.secondary}>
              <Button label="Skip for now" variant="ghost" onPress={() => router.replace('/')} />
            </View>
          </>
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  content: {
    paddingHorizontal: space.s6,
    paddingBottom: space.s9,
    flexGrow: 1,
    justifyContent: 'center',
  },
  wordmark: { fontSize: 36, lineHeight: 40 },
  lead: { marginTop: space.s2, marginBottom: space.s6 },
  secondary: { marginTop: space.s2 },
});
