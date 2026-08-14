import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { ApiError } from '@/api/client';
import { useManualPortfolio } from '@/api/onboarding';
import { Step } from '@/onboarding/Step';
import { hasBeenPrimed, isFreeBuild } from '@/push/register';
import { color, radius, space, type, HIT_SLOP } from '@/theme/tokens';
import { Button, ErrorNote, Txt } from '@/ui';

type Row = { id: number; ticker: string; quantity: string };

const MAX_ROWS = 30;

/**
 * The manual fallback — the answer to the funnel's biggest drop-off, users who
 * won't link a brokerage to an unknown app on day one.
 *
 * Cost basis is unknowable for typed entries, so the server records today's
 * price as the average cost and returns are measured from entry. That is
 * stated here rather than discovered later as a wrong-looking number.
 */
export default function ManualStep() {
  const router = useRouter();
  const save = useManualPortfolio();
  const [rows, setRows] = useState<Row[]>([{ id: 1, ticker: '', quantity: '' }]);
  const [error, setError] = useState<string | null>(null);

  const update = (id: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const filled = rows.filter((r) => r.ticker.trim() && Number(r.quantity) > 0);

  const submit = async () => {
    setError(null);
    if (!filled.length) {
      setError('Enter at least one holding.');
      return;
    }
    try {
      await save.mutateAsync(
        filled.map((r) => ({
          ticker: r.ticker.trim().toUpperCase(),
          quantity: Number(r.quantity),
        })),
      );
      if (!hasBeenPrimed() && !isFreeBuild()) router.push('/push-priming');
      else router.push('/(onboarding)/risk');
    } catch (e) {
      setError(
        e instanceof ApiError ? e.detail : 'Could not save those holdings. Try again.',
      );
    }
  };

  return (
    <Step
      step={2}
      title="Enter your holdings"
      blurb="Ticker and share count is enough. You can connect a brokerage later and this gets replaced."
      onSkip={() => router.push('/(onboarding)/risk')}
      skipLabel="Later"
      footer={
        <>
          <Button
            label={`Save ${filled.length || ''} holding${filled.length === 1 ? '' : 's'}`.replace(
              '  ',
              ' ',
            )}
            onPress={submit}
            loading={save.isPending}
            disabled={!filled.length}
          />
          <Txt variant="caption" tone="ink3" center>
            Returns are measured from today, since a typed holding has no cost basis.
          </Txt>
        </>
      }
    >
      {error ? <ErrorNote message={error} /> : null}

      <View style={styles.head}>
        <Txt variant="label" tone="ink3" uppercase style={styles.tickerCol}>
          Ticker
        </Txt>
        <Txt variant="label" tone="ink3" uppercase style={styles.qtyCol}>
          Shares
        </Txt>
        <View style={styles.removeCol} />
      </View>

      {rows.map((row) => (
        <View key={row.id} style={styles.row}>
          <TextInput
            style={[styles.input, styles.tickerCol]}
            value={row.ticker}
            onChangeText={(t) => update(row.id, { ticker: t.toUpperCase() })}
            placeholder="NVDA"
            placeholderTextColor={color.ink3}
            autoCapitalize="characters"
            autoCorrect={false}
            selectionColor={color.accent}
            accessibilityLabel="Ticker"
          />
          <TextInput
            style={[styles.input, styles.qtyCol]}
            value={row.quantity}
            onChangeText={(t) => update(row.id, { quantity: t.replace(/[^0-9.]/g, '') })}
            placeholder="10"
            placeholderTextColor={color.ink3}
            keyboardType="decimal-pad"
            selectionColor={color.accent}
            accessibilityLabel="Share count"
          />
          <Pressable
            onPress={() => setRows((prev) => (prev.length > 1 ? prev.filter((r) => r.id !== row.id) : prev))}
            hitSlop={HIT_SLOP}
            accessibilityRole="button"
            accessibilityLabel={`Remove ${row.ticker || 'row'}`}
            style={styles.removeCol}
          >
            <Txt variant="body" tone="ink3">
              ✕
            </Txt>
          </Pressable>
        </View>
      ))}

      {rows.length < MAX_ROWS ? (
        <Button
          label="Add another"
          variant="ghost"
          size="sm"
          onPress={() =>
            setRows((prev) => [...prev, { id: (prev.at(-1)?.id ?? 0) + 1, ticker: '', quantity: '' }])
          }
        />
      ) : (
        <Txt variant="caption" tone="ink3">
          That&apos;s the maximum of {MAX_ROWS} typed holdings.
        </Txt>
      )}
    </Step>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', gap: space.s2, marginBottom: space.s1 },
  row: { flexDirection: 'row', gap: space.s2, marginBottom: space.s2, alignItems: 'center' },
  input: {
    backgroundColor: color.surface2,
    borderWidth: 1,
    borderColor: color.lineStrong,
    borderRadius: radius.m,
    paddingHorizontal: space.s3,
    paddingVertical: space.s3,
    fontSize: type.body.fontSize,
    color: color.ink,
  },
  tickerCol: { flex: 2 },
  qtyCol: { flex: 1 },
  removeCol: { width: 28, alignItems: 'center' },
});
