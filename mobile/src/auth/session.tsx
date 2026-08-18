import type { Session } from '@supabase/supabase-js';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { setSignOutHandler } from '@/api/client';
import { clearAllCaches } from '@/api/storage';
import { startSessionAutoRefresh, supabase } from '@/auth/supabase';
import { API_BASE } from '@/config';
import { disablePush } from '@/push/register';

type SessionState = {
  session: Session | null;
  /** False until the stored session has been read off the Keychain. */
  ready: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  sendPasswordReset: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setReady(true);
    });

    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
    });

    const stopRefresh = startSessionAutoRefresh();

    return () => {
      active = false;
      sub.subscription.unsubscribe();
      stopRefresh();
    };
  }, []);

  const value = useMemo<SessionState>(() => {
    /**
     * Signing out wipes every local cache as well as the session. Portfolio
     * data left in MMKV after a sign-out is a privacy finding, and the next
     * account to sign in on this device must not inherit it.
     */
    const signOut = async () => {
      // Unregister first: after signOut the bearer token is gone and the
      // device would keep receiving the previous account's notifications.
      await disablePush();
      await supabase.auth.signOut();
      clearAllCaches();
      setSession(null);
    };

    return {
      session,
      ready,
      signIn: async (email, password) => {
        const { error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });
        if (error) throw error;
      },
      signUp: async (email, password) => {
        const { error } = await supabase.auth.signUp({
          email: email.trim(),
          password,
        });
        if (error) throw error;
      },
      sendPasswordReset: async (email) => {
        // Not the scheme directly: email clients won't reliably follow a
        // redirect to cirvia://, and the recovery tokens ride in the URL
        // fragment. The web bridge reads the fragment and hands off to
        // cirvia://reset (see /app/auth/bridge in app/webapp.py). Must be
        // in the Supabase Auth redirect allowlist.
        const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
          redirectTo: `${API_BASE}/app/auth/bridge`,
        });
        if (error) throw error;
      },
      signOut,
    };
  }, [session, ready]);

  // The API client signs out on a refresh failure, but it must not import
  // React state to do it; it gets the handler by injection instead.
  useEffect(() => {
    setSignOutHandler(value.signOut);
  }, [value.signOut]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useSession must be used inside <SessionProvider>');
  return ctx;
}
