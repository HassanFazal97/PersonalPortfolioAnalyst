import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useSession } from '@/auth/session';
import { color, space } from '@/theme/tokens';
import { Button, Field, Txt } from '@/ui';

type Mode = 'sign-in' | 'sign-up';

export default function SignIn() {
  const { signIn, signUp, sendPasswordReset } = useSession();
  const insets = useSafeAreaInsets();

  const [mode, setMode] = useState<Mode>('sign-in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    setNotice(null);
    if (!email.trim() || !password) {
      setError('Enter your email and password.');
      return;
    }
    if (mode === 'sign-up' && password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'sign-in') {
        await signIn(email, password);
      } else {
        await signUp(email, password);
        setNotice('Check your email to confirm your account, then sign in.');
        setMode('sign-in');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!email.trim()) {
      setError('Enter your email first, then tap Forgot password.');
      return;
    }
    setError(null);
    try {
      await sendPasswordReset(email);
      setNotice('Password reset sent. Check your email.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send the reset email.');
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
        <Txt variant="body" tone="ink2" style={styles.lead}>
          The AI analyst that shows its work. Sign in to pick up where the web left off.
        </Txt>

        <Field
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="emailAddress"
          returnKeyType="next"
        />
        <Field
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'}
          textContentType={mode === 'sign-in' ? 'password' : 'newPassword'}
          returnKeyType={mode === 'sign-in' ? 'go' : 'next'}
          onSubmitEditing={mode === 'sign-in' ? submit : undefined}
          error={mode === 'sign-in' ? error : undefined}
        />
        {mode === 'sign-up' ? (
          <Field
            label="Confirm password"
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
            autoCapitalize="none"
            autoComplete="new-password"
            textContentType="newPassword"
            returnKeyType="go"
            onSubmitEditing={submit}
            error={error}
          />
        ) : null}

        {notice ? (
          <Txt variant="bodySm" tone="accent" style={styles.notice}>
            {notice}
          </Txt>
        ) : null}

        <Button
          label={mode === 'sign-in' ? 'Sign in' : 'Create account'}
          onPress={submit}
          loading={busy}
        />
        <View style={styles.secondary}>
          <Button
            label={mode === 'sign-in' ? 'Create an account' : 'I already have an account'}
            variant="ghost"
            onPress={() => {
              setMode(mode === 'sign-in' ? 'sign-up' : 'sign-in');
              setConfirmPassword('');
              setError(null);
              setNotice(null);
            }}
          />
        </View>

        {mode === 'sign-in' ? (
          <View style={styles.forgot}>
            <Button label="Forgot your password?" variant="link" onPress={reset} />
          </View>
        ) : null}

        <Txt variant="caption" tone="ink3" center style={styles.footnote}>
          Your session is stored in the device keychain, never in plain app storage.
        </Txt>
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
  notice: { marginBottom: space.s3 },
  secondary: { marginTop: space.s2 },
  forgot: { alignItems: 'center', marginTop: space.s2 },
  footnote: { marginTop: space.s7 },
});
