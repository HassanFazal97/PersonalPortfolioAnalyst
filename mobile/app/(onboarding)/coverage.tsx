import { useRouter } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';

import { useDashboard } from '@/api/bootstrap';
import { ApiError } from '@/api/client';
import { useSavePreferences } from '@/api/onboarding';
import { groupByTicker } from '@/dashboard/portfolio';
import { Choice, Step } from '@/onboarding/Step';
import { Button, Card, ErrorNote, Txt } from '@/ui';

/**
 * Step 5: which holdings get news coverage in the digest.
 *
 * Only meaningful on Free, where the plan caps how many holdings the digest
 * can research. Pro covers everything, so the step auto-advances rather than
 * asking a question with one possible answer.
 */
export default function CoverageStep() {
  const router = useRouter();
  const { data } = useDashboard();
  const save = useSavePreferences();

  const me = data?.sections.me.value;
  const positions = data?.sections.portfolio.value?.positions ?? [];
  const tickers = useMemo(
    () => groupByTicker(positions).map((h) => h.ticker).sort(),
    [positions],
  );

  const cap = me?.digest_tickers_limit ?? null;
  const editable = me?.digest_tickers_editable ?? false;
  const [picked, setPicked] = useState<string[]>([]);

  useEffect(() => {
    if (me?.digest_tickers?.length) setPicked(me.digest_tickers);
    else if (cap != null) setPicked(tickers.slice(0, cap));
  }, [me?.digest_tickers, cap, tickers]);

  // Nothing to choose: Pro, or fewer holdings than the cap.
  useEffect(() => {
    if (data && !editable) router.replace('/(onboarding)/schedule');
  }, [data, editable, router]);

  const toggle = (ticker: string) => {
    setPicked((prev) => {
      if (prev.includes(ticker)) return prev.filter((t) => t !== ticker);
      if (cap != null && prev.length >= cap) return prev;
      return [...prev, ticker];
    });
  };

  const submit = async () => {
    try {
      await save.mutateAsync({ digest_tickers: picked });
      router.push('/(onboarding)/schedule');
    } catch {
      // Surfaced below.
    }
  };

  return (
    <Step
      step={5}
      title="Choose your coverage"
      blurb={
        cap != null
          ? `Your plan researches news for ${cap} holdings. The rest still count toward your portfolio numbers.`
          : 'Pick which holdings get news in your digest.'
      }
      onSkip={() => router.push('/(onboarding)/schedule')}
      footer={
        <Button
          label="Continue"
          onPress={submit}
          loading={save.isPending}
          disabled={!picked.length}
        />
      }
    >
      {save.isError ? (
        <ErrorNote
          message={
            save.error instanceof ApiError
              ? save.error.detail
              : 'Could not save your coverage. Try again.'
          }
        />
      ) : null}

      {tickers.length ? (
        <>
          <Txt variant="caption" tone="ink3">
            {picked.length}
            {cap != null ? ` of ${cap}` : ''} selected
          </Txt>
          {tickers.map((ticker) => (
            <Choice
              key={ticker}
              label={ticker}
              multi
              selected={picked.includes(ticker)}
              onPress={() => toggle(ticker)}
            />
          ))}
        </>
      ) : (
        <Card>
          <Txt variant="bodySm" tone="ink3">
            No holdings yet — once you connect a brokerage or type some in, this is where
            you pick which ones get news.
          </Txt>
        </Card>
      )}
    </Step>
  );
}
