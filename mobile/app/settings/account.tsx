import { useState } from 'react';

import { useDashboard } from '@/api/bootstrap';
import { ApiError } from '@/api/client';
import { useSavePreferences } from '@/api/onboarding';
import { Group, Row, SettingsScreen } from '@/settings/Section';
import { space } from '@/theme/tokens';
import { Button, ErrorNote, Txt } from '@/ui';

/** The digest send times the scheduler can actually honour (it runs hourly). */
const TIMES = ['07:00', '08:00', '09:00', '12:00', '17:00'] as const;

function label(hhmm: string): string {
  const [h] = hhmm.split(':');
  const hour = Number(h);
  const suffix = hour >= 12 ? 'PM' : 'AM';
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${twelve}:00 ${suffix}`;
}

export default function AccountScreen() {
  const { data, refetch } = useDashboard();
  const save = useSavePreferences();
  const [error, setError] = useState<string | null>(null);

  const me = data?.sections.me.value;
  const current = me?.digest_send_time?.slice(0, 5) ?? '09:00';

  const update = async (patch: Parameters<typeof save.mutateAsync>[0]) => {
    setError(null);
    try {
      await save.mutateAsync(patch);
      await refetch();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Could not save that. Try again.');
    }
  };

  return (
    <SettingsScreen title="Account">
      {error ? <ErrorNote message={error} /> : null}

      <Group label="You">
        <Row label="Email" value={me?.email ?? '—'} />
        <Row label="Timezone" value={me?.timezone ?? '—'} />
      </Group>

      <Group label="Digest">
        <Row
          label="Send the digest"
          value={me?.digest_enabled ? 'On' : 'Paused'}
          right={
            <Button
              label={me?.digest_enabled ? 'Pause' : 'Resume'}
              variant="link"
              onPress={() => void update({ digest_enabled: !me?.digest_enabled })}
            />
          }
        />
        {TIMES.map((t) => (
          <Row
            key={t}
            label={label(t)}
            value={current === t ? 'Selected' : undefined}
            onPress={() => void update({ digest_send_time: t })}
          />
        ))}
      </Group>

      <Txt variant="caption" tone="ink3" style={styles.note}>
        Times are in {me?.timezone ?? 'your local timezone'}. Your email address is managed
        from your account on cirvia.ca.
      </Txt>
    </SettingsScreen>
  );
}

const styles = { note: { marginTop: space.s2 } } as const;
