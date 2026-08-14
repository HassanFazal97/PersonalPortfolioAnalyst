/**
 * Dynamic config layered over app.json.
 *
 * Expo reads app.json first and passes it here as `config`, so app.json stays
 * the single source of truth for the real build and this file only subtracts
 * from it.
 *
 * `EXPO_FREE_BUILD=1` strips the two capabilities that require a paid Apple
 * Developer Program membership, so the app can be signed by a free "Personal
 * Team" and run on a physical iPhone:
 *
 *   - Associated Domains (universal links)
 *   - Push notifications (the APNs entitlement, which expo-notifications
 *     always sets to "development")
 *
 * Leaving either in place makes provisioning fail outright with a free
 * account — Xcode cannot create a profile for an entitlement the team does
 * not have.
 *
 * You do NOT need this for the iOS Simulator, which requires no provisioning
 * profile and no Apple account at all. It is only for running on real
 * hardware without paying yet.
 *
 *   EXPO_FREE_BUILD=1 npx expo run:ios --device
 *
 * Everything else still works on a free build, including the custom `cirvia://`
 * scheme — URL schemes need no entitlement, so the SnapTrade and Discord
 * round-trips behave exactly as they do in production.
 */

const { withEntitlementsPlist } = require('expo/config-plugins');

const FREE_BUILD = process.env.EXPO_FREE_BUILD === '1';

/** Plugin entries are either "name" or ["name", {...}]. */
function withoutPlugin(plugins, name) {
  return (plugins ?? []).filter((entry) =>
    Array.isArray(entry) ? entry[0] !== name : entry !== name,
  );
}

/**
 * Strip `aps-environment` from the generated entitlements.
 *
 * Dropping expo-notifications from `plugins` is not enough: Expo auto-applies
 * the config plugin of any *installed* package, so the push entitlement comes
 * back regardless. This mod runs last and deletes it.
 *
 * It does not block a Simulator build — Expo only demands signing on a
 * simulator for `associated-domains` and `applesignin` — but it does block
 * provisioning on a free Personal Team, which is the whole point of the flag.
 */
const withoutPushEntitlement = (config) =>
  withEntitlementsPlist(config, (mod) => {
    delete mod.modResults['aps-environment'];
    return mod;
  });

module.exports = ({ config }) => {
  if (!FREE_BUILD) return config;

  const { associatedDomains, ...ios } = config.ios ?? {};

  return withoutPushEntitlement({
    ...config,
    // Distinguishable on the home screen next to a real build.
    name: `${config.name} (free)`,
    ios: {
      ...ios,
      // A personal team that claims ca.cirvia.app can block registering the
      // same id under the real team later, so free builds take their own.
      bundleIdentifier: `${config.ios?.bundleIdentifier}.free`,
    },
    plugins: withoutPlugin(config.plugins, 'expo-notifications'),
    extra: {
      ...(config.extra ?? {}),
      // Read by the client so push registration is skipped rather than
      // attempted and failed. `enablePush` already tolerates a missing token,
      // but this keeps the permission prompt from being spent for nothing.
      freeBuild: true,
    },
  });
};
