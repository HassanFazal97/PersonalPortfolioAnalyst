import type { Dashboard } from '@/api/bootstrap';
import type { Notifications, PortfolioStatus } from '@/api/types';

/**
 * Which dashboard banners to show, and in what order.
 *
 * The web scatters this across four `check*` functions that read each other's
 * `style.display` to enforce "one nudge at a time". That precedence is real
 * product behaviour, so it lives here as one ordered pass instead — the same
 * rules, in a form that can be reasoned about and tested.
 */

export type BannerId = 'trial' | 'connection' | 'delivery' | 'personalize';

export type BannerSpec = {
  id: BannerId;
  tone: 'warn' | 'setup';
  title: string;
  body: string;
  actionLabel?: string;
  /** Absent for the trial banner: a paused digest is not dismissible. */
  dismissible: boolean;
};

/**
 * A brokerage link that existed and is broken now. A fresh account that never
 * connected keeps its empty state instead — it is not broken, just empty.
 */
export function connectionBroken(status: PortfolioStatus | null): boolean {
  if (!status?.registered) return false;
  return Boolean(
    status.connection_disabled ||
      status.last_sync_error ||
      (!status.connected && status.last_sync_at),
  );
}

/** No verified, non-opted-out channel matching the user's preference. */
export function deliveryUnset(notifications: Notifications | null): boolean {
  if (!notifications) return false;
  const active = notifications.channels.find(
    (c) => c.channel === notifications.preferred_channel,
  );
  return !(active && active.verified && !active.opted_out);
}

export function selectBanners(
  dashboard: Dashboard | undefined,
  dismissed: ReadonlySet<BannerId>,
): BannerSpec[] {
  if (!dashboard) return [];
  const me = dashboard.sections.me.value;
  const status = dashboard.sections.status.value;
  const notifications = dashboard.sections.notifications.value;
  const out: BannerSpec[] = [];

  // Always first, never dismissible: digests are paused until this is answered.
  if (me?.trial.decision_pending) {
    out.push({
      id: 'trial',
      tone: 'warn',
      title: 'Your Pro trial has ended and your digests are paused.',
      body:
        'Continue on Free to start receiving them again. If you do nothing, ' +
        "we'll move you to Free automatically in about a week.",
      actionLabel: 'Continue on Free',
      dismissible: false,
    });
  }

  // One nudge at a time, most urgent first: a broken brokerage link makes the
  // digest wrong, an unset channel makes it undelivered, and personalisation
  // only makes it better.
  if (!dismissed.has('connection') && connectionBroken(status)) {
    out.push({
      id: 'connection',
      tone: 'warn',
      title: 'Your brokerage connection needs attention.',
      body: 'Your digest may be out of date until you reconnect.',
      actionLabel: 'Reconnect',
      dismissible: true,
    });
    return out;
  }

  if (!dismissed.has('delivery') && deliveryUnset(notifications)) {
    out.push({
      id: 'delivery',
      tone: 'setup',
      title: 'Get your digest delivered.',
      body: 'Add text, email, or Discord and your morning brief reaches you before the market opens.',
      actionLabel: 'Set up delivery',
      dismissible: true,
    });
    return out;
  }

  const profile = me?.profile;
  if (
    !dismissed.has('personalize') &&
    profile &&
    !profile.completed &&
    !profile.prompt_dismissed
  ) {
    out.push({
      id: 'personalize',
      tone: 'setup',
      title: 'Make Cirvia yours.',
      body: 'Answer three quick questions so your digest, news, and risk analysis fit how you invest.',
      actionLabel: 'Personalize now',
      dismissible: true,
    });
  }

  return out;
}
