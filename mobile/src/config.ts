/**
 * Build-time configuration.
 *
 * `EXPO_PUBLIC_*` variables are inlined by Metro at build time, so they are
 * readable in the bundle — which is correct for all three of these. The
 * Supabase anon key is a publishable key (the web app ships it in every page)
 * and the API base is a public hostname. Nothing secret belongs here.
 */

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `Missing ${name}. Copy mobile/.env.example to mobile/.env and fill it in, ` +
        'then restart the dev server (Metro inlines these at build time).',
    );
  }
  return value.replace(/\/+$/, '');
}

export const API_BASE = required('EXPO_PUBLIC_API_BASE', process.env.EXPO_PUBLIC_API_BASE);

export const SUPABASE_URL = required(
  'EXPO_PUBLIC_SUPABASE_URL',
  process.env.EXPO_PUBLIC_SUPABASE_URL,
);

export const SUPABASE_ANON_KEY = required(
  'EXPO_PUBLIC_SUPABASE_ANON_KEY',
  process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY,
);

/** Deep-link scheme, kept in step with `scheme` in app.json. */
export const APP_SCHEME = 'cirvia';
