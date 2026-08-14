import { useLocalSearchParams, useRouter } from 'expo-router';
import { View } from 'react-native';

import { ApiError } from '@/api/client';
import { POSTURES, useProjections, useSaveProfile, type PostureKey } from '@/api/onboarding';
import { fmtCurCompact, fmtSignedPct } from '@/format';
import { Choice, Step } from '@/onboarding/Step';
import { useOnboardingDraft } from '@/onboarding/state';
import { space } from '@/theme/tokens';
import { Button, Card, ErrorNote, SkeletonBlock, Txt } from '@/ui';

/**
 * Step 4: the same portfolio at three risk levels, with the numbers that
 * actually matter to a person — the bad case in dollars, not a volatility
 * figure.
 *
 * This is where the profile is written, in one `PUT /me/profile` carrying the
 * step-1 answers and the chosen posture together.
 */
export default function RiskStep() {
  const router = useRouter();
  const { personalize } = useLocalSearchParams<{ personalize?: string }>();
  const { draft, set } = useOnboardingDraft();
  const projections = useProjections();
  const save = useSaveProfile();

  const chosen = draft.chosen_posture;

  const commit = async (posture?: PostureKey) => {
    try {
      await save.mutateAsync({ ...draft, chosen_posture: posture });
      // Re-personalizing ends here; first-run continues through the wizard.
      if (personalize === '1') router.replace('/(tabs)');
      else router.push('/(onboarding)/coverage');
    } catch {
      // Surfaced below; the user can retry or skip on.
    }
  };

  return (
    <Step
      step={4}
      title="Risk comfort"
      blurb="Your real portfolio at three risk levels. Pick the one you could sleep through."
      onSkip={() => void commit(undefined)}
      footer={
        <Button
          label="Continue"
          onPress={() => void commit(chosen)}
          loading={save.isPending}
          disabled={!chosen}
        />
      }
    >
      {save.isError ? (
        <ErrorNote
          message={
            save.error instanceof ApiError
              ? save.error.detail
              : 'Could not save your profile. Try again.'
          }
        />
      ) : null}

      {projections.isLoading ? (
        <Card>
          <SkeletonBlock lines={4} />
        </Card>
      ) : null}

      {projections.data?.fallback ? (
        <Txt variant="caption" tone="ink3" style={styles.note}>
          These are illustrative until your holdings have enough history to model.
        </Txt>
      ) : null}

      {POSTURES.map((posture) => {
        const block = projections.data?.postures?.[posture.key];
        const worstPct = block?.terminal_pct.p5;
        const worstCad = block?.terminal_cad?.p5;
        const medianPct = block?.terminal_pct.p50;

        const hint = block
          ? `Bad year: ${fmtSignedPct(worstPct ?? null)}` +
            (worstCad != null ? ` · ${fmtCurCompact(worstCad)}` : '') +
            `\nTypical: ${fmtSignedPct(medianPct ?? null)}`
          : undefined;

        return (
          <Choice
            key={posture.key}
            label={posture.label}
            hint={hint}
            selected={chosen === posture.key}
            onPress={() => set({ chosen_posture: posture.key })}
          />
        );
      })}

      <View style={styles.note}>
        <Txt variant="caption" tone="ink3">
          This sets what your digest flags as risk. It never trades for you, and you can
          change it any time.
        </Txt>
      </View>
    </Step>
  );
}

const styles = { note: { marginTop: space.s2 } } as const;
