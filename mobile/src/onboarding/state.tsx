import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

import { prefs, readJson, writeJson } from '@/api/storage';
import type { ProfileDraft } from '@/api/onboarding';

/**
 * Answers collected across the wizard.
 *
 * They are held here rather than written step by step because `PUT /me/profile`
 * is one write for the whole flow — that is deliberate server-side, so a user
 * who abandons mid-wizard never ends up with a half-built profile that the
 * digest then treats as their real preferences. Persisted to MMKV so killing
 * the app between steps doesn't lose the answers either.
 */

const DRAFT_KEY = 'onboarding:draft';

type DraftState = {
  draft: ProfileDraft;
  set: (patch: Partial<ProfileDraft>) => void;
  clear: () => void;
};

const EMPTY: ProfileDraft = { goals: [] };

const Ctx = createContext<DraftState | null>(null);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [draft, setDraft] = useState<ProfileDraft>(
    () => readJson<ProfileDraft>(prefs, DRAFT_KEY) ?? EMPTY,
  );

  const set = useCallback((patch: Partial<ProfileDraft>) => {
    setDraft((prev) => {
      const next = { ...prev, ...patch };
      writeJson(prefs, DRAFT_KEY, next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    prefs.remove(DRAFT_KEY);
    setDraft(EMPTY);
  }, []);

  const value = useMemo(() => ({ draft, set, clear }), [draft, set, clear]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useOnboardingDraft(): DraftState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useOnboardingDraft must be used inside <OnboardingProvider>');
  return ctx;
}
