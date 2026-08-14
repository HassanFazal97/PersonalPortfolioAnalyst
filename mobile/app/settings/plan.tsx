import { useCallback, useState } from 'react';
import { View } from 'react-native';

import { BOOTSTRAP_PATH, useDashboard } from '@/api/bootstrap';
import { api, ApiError } from '@/api/client';
import { invalidateCached } from '@/api/etag';
import { Group, Row, SettingsScreen } from '@/settings/Section';
import { space } from '@/theme/tokens';
import { Button, ErrorNote, Txt } from '@/ui';

/**
 * Status only. No price, no upgrade button, no link to checkout — the app
 * never sells a subscription, so there is no purchase surface to be rejected
 * for. Plan changes happen on the web.
 *
 * The one action here is "Continue on the Free plan", which is not a purchase:
 * it unblocks a user stuck in the trial-decision gate with their digests
 * paused, which would otherwise be a dead end inside the app.
 */
export default function PlanScreen() {
  const { data, refetch } = useDashboard();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const me = data?.sections.me.value;
  const trial = me?.trial;
  const quota = me?.chat_quota;
  const plan = me?.effective_plan ?? me?.plan ?? 'free';

  const heading = trial?.active
    ? 'Pro trial'
    : trial?.decision_pending
      ? 'Trial ended'
      : plan === 'pro'
        ? 'Pro'
        : 'Free';

  const subheading = trial?.active
    ? trial.ends_at
      ? `Your full Pro trial runs until ${new Date(trial.ends_at).toLocaleDateString()}.`
      : 'Your full Pro trial is running.'
    : trial?.decision_pending
      ? 'Your digests are paused until you choose a plan.'
      : plan === 'pro'
        ? 'Everything is included.'
        : 'Your digest keeps running on the Free plan.';

  const chooseFree = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      await api('/billing/choose-free', { method: 'POST' });
      invalidateCached(BOOTSTRAP_PATH);
      await refetch();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Could not update your plan. Try again.');
    } finally {
      setBusy(false);
    }
  }, [refetch]);

  return (
    <SettingsScreen title="Plan">
      {error ? <ErrorNote message={error} /> : null}

      <View style={styles.hero}>
        <Txt variant="title" tone="ink" center>
          {heading}
        </Txt>
        <Txt variant="bodySm" tone="ink3" center>
          {subheading}
        </Txt>
      </View>

      <Group label="What you have">
        <Row
          label="Holdings covered"
          value={
            me?.digest_tickers_limit == null
              ? 'All'
              : `${me.digest_tickers.length} of ${me.digest_tickers_limit}`
          }
        />
        <Row
          label="Chat questions"
          value={
            quota?.remaining == null
              ? 'Included'
              : `${quota.remaining} left${quota.limit ? ` of ${quota.limit}` : ''}`
          }
        />
        <Row label="Model Picks" value={plan === 'pro' ? 'Included' : 'Pro only'} />
        <Row label="Deep dives" value={plan === 'pro' ? 'Included' : 'Limited on Free'} />
        <Row
          label="Renews"
          value={
            me?.billing.current_period_end
              ? new Date(me.billing.current_period_end).toLocaleDateString()
              : '—'
          }
        />
      </Group>

      {trial?.decision_pending ? (
        <>
          <Button label="Continue on the Free plan" variant="ghost" onPress={chooseFree} loading={busy} />
          <Txt variant="caption" tone="ink3" center style={styles.note}>
            Free keeps your digest and covers a few holdings. You can change your plan any
            time from your account on cirvia.ca.
          </Txt>
        </>
      ) : (
        <Txt variant="caption" tone="ink3" center style={styles.note}>
          Manage your plan from your account on cirvia.ca.
        </Txt>
      )}
    </SettingsScreen>
  );
}

const styles = { hero: { paddingVertical: space.s6, gap: space.s1 }, note: { marginTop: space.s3 } } as const;
