import { useRouter } from 'expo-router';
import { useState } from 'react';

import { useDashboard } from '@/api/bootstrap';
import { ApiError } from '@/api/client';
import { useSavePreferences } from '@/api/onboarding';
import { Choice, Step } from '@/onboarding/Step';
import { Button, ErrorNote, Txt } from '@/ui';

/**
 * Step 6: when the digest arrives.
 *
 * Fixed options rather than a time picker — the digest is written by a job
 * that runs on the hour, so a 9:37 choice would be a promise the scheduler
 * cannot keep.
 */
const TIMES = [
  { key: '07:00', label: '7:00 AM', hint: 'Before you leave' },
  { key: '08:00', label: '8:00 AM', hint: 'With breakfast' },
  { key: '09:00', label: '9:00 AM', hint: 'Just before the open' },
  { key: '12:00', label: '12:00 PM', hint: 'Midday check-in' },
  { key: '17:00', label: '5:00 PM', hint: 'After the close' },
] as const;

export default function ScheduleStep() {
  const router = useRouter();
  const { data } = useDashboard();
  const save = useSavePreferences();
  const [time, setTime] = useState<string>(
    () => data?.sections.me.value?.digest_send_time?.slice(0, 5) ?? '09:00',
  );

  const submit = async () => {
    try {
      await save.mutateAsync({ digest_send_time: time, digest_enabled: true });
      router.push('/(onboarding)/delivery');
    } catch {
      // Surfaced below.
    }
  };

  return (
    <Step
      step={6}
      title="When should it arrive?"
      blurb="Your morning brief is written fresh each market day, from your actual holdings."
      onSkip={() => router.push('/(onboarding)/delivery')}
      footer={<Button label="Continue" onPress={submit} loading={save.isPending} />}
    >
      {save.isError ? (
        <ErrorNote
          message={
            save.error instanceof ApiError
              ? save.error.detail
              : 'Could not save your send time. Try again.'
          }
        />
      ) : null}

      {TIMES.map((t) => (
        <Choice
          key={t.key}
          label={t.label}
          hint={t.hint}
          selected={time === t.key}
          onPress={() => setTime(t.key)}
        />
      ))}

      <Txt variant="caption" tone="ink3">
        Times are in {data?.sections.me.value?.timezone ?? 'your local timezone'}.
      </Txt>
    </Step>
  );
}
