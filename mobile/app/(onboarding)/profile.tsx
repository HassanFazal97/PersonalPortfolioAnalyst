import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { EXPERIENCE_LEVELS, GOALS, HORIZONS } from '@/api/onboarding';
import { Choice, Step } from '@/onboarding/Step';
import { useOnboardingDraft } from '@/onboarding/state';
import { Button, Txt } from '@/ui';

type Question = 'horizon' | 'experience' | 'goals';
const ORDER: Question[] = ['horizon', 'experience', 'goals'];

/**
 * Step 1, as three questions on one screen rather than three screens: on a
 * phone the whole set fits, and a three-tap flow with two transitions between
 * taps reads as longer than it is.
 */
export default function ProfileStep() {
  const router = useRouter();
  // Re-personalizing from settings: the portfolio already exists, so the
  // questions hand straight to the risk picker rather than walking a
  // set-up user back through connect, coverage, and delivery.
  const { personalize } = useLocalSearchParams<{ personalize?: string }>();
  const rePersonalizing = personalize === '1';
  const nextRoute = rePersonalizing
    ? ('/(onboarding)/risk?personalize=1' as const)
    : ('/(onboarding)/connect' as const);
  const { draft, set } = useOnboardingDraft();
  const [question, setQuestion] = useState(0);

  const current = ORDER[question]!;
  const answered =
    current === 'goals'
      ? draft.goals.length > 0
      : current === 'horizon'
        ? !!draft.horizon
        : !!draft.experience;

  const next = () => {
    if (question < ORDER.length - 1) setQuestion(question + 1);
    else router.push(nextRoute);
  };

  return (
    <Step
      step={1}
      title={
        current === 'horizon'
          ? 'How long do you usually hold?'
          : current === 'experience'
            ? 'How long have you been investing?'
            : "What are you investing for?"
      }
      blurb={
        current === 'goals'
          ? 'Pick as many as apply. This sets what your digest treats as worth mentioning.'
          : 'How you invest, so Cirvia can speak your language.'
      }
      onBack={question > 0 ? () => setQuestion(question - 1) : () => router.back()}
      onSkip={() => router.push(nextRoute)}
      footer={
        <>
          <Button label="Continue" onPress={next} disabled={!answered} />
          <Txt variant="caption" tone="ink3" center>
            {question + 1} of {ORDER.length}
          </Txt>
        </>
      }
    >
      <View>
        {current === 'horizon'
          ? HORIZONS.map((h) => (
              <Choice
                key={h.key}
                label={h.label}
                hint={h.hint}
                selected={draft.horizon === h.key}
                onPress={() => set({ horizon: h.key })}
              />
            ))
          : null}

        {current === 'experience'
          ? EXPERIENCE_LEVELS.map((e) => (
              <Choice
                key={e.key}
                label={e.label}
                selected={draft.experience === e.key}
                onPress={() => set({ experience: e.key })}
              />
            ))
          : null}

        {current === 'goals'
          ? GOALS.map((g) => (
              <Choice
                key={g.key}
                label={g.label}
                multi
                selected={draft.goals.includes(g.key)}
                onPress={() =>
                  set({
                    goals: draft.goals.includes(g.key)
                      ? draft.goals.filter((x) => x !== g.key)
                      : [...draft.goals, g.key],
                  })
                }
              />
            ))
          : null}
      </View>
    </Step>
  );
}
