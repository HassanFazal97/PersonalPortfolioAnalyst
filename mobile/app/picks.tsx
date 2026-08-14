import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError } from '@/api/client';
import { usePicks, type Pick } from '@/api/reports';
import { fmtSignedPct } from '@/format';
import { color, radius, space, HIT_SLOP } from '@/theme/tokens';
import { Card, EmptyState, ErrorNote, SkeletonBlock, Tag, Txt } from '@/ui';

export default function PicksScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data, isLoading, error, refetch } = usePicks();

  const gated = error instanceof ApiError && error.status === 402;

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.nav}>
        <Pressable onPress={() => router.back()} hitSlop={HIT_SLOP} accessibilityRole="button">
          <Txt variant="body" tone="accent">
            ‹ Back
          </Txt>
        </Pressable>
        <Txt variant="cardTitle" tone="ink">
          Model Picks
        </Txt>
        <View style={styles.navSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {gated ? (
          <EmptyState
            title="A Pro feature"
            body={
              'The daily ranked candidates, with verified evidence and a public track ' +
              'record, are part of Cirvia Pro. Manage your plan on cirvia.ca.'
            }
          />
        ) : null}

        {error && !gated ? (
          <ErrorNote message="Could not load today's analysis." onRetry={() => void refetch()} />
        ) : null}

        {isLoading ? (
          <Card>
            <SkeletonBlock lines={4} />
          </Card>
        ) : null}

        {data && !data.available ? (
          <EmptyState title="Nothing yet today" body={data.note} />
        ) : null}

        {data?.available ? (
          <>
            <Txt variant="bodySm" tone="ink3">
              Every market morning a quantitative screen ranks ~560 US and Canadian large
              caps; analyst agents research the strongest, and a verifier re-checks every
              claim.
            </Txt>

            {data.stale ? (
              <Txt variant="caption" tone="warn" style={styles.gap}>
                {data.stale_note}
              </Txt>
            ) : null}

            {data.headline ? (
              <Card title={data.headline}>
                {data.overview ? (
                  <Txt variant="bodySm" tone="ink2">
                    {data.overview}
                  </Txt>
                ) : null}
              </Card>
            ) : null}

            {data.movers?.length ? (
              <Card title="What's moving">
                {data.movers.slice(0, 5).map((m) => (
                  <View key={m.ticker} style={styles.mover}>
                    <View style={styles.moverMain}>
                      <Txt variant="cardTitle" tone="ink">
                        {m.ticker}
                      </Txt>
                      {m.catalyst ? (
                        <Txt variant="caption" tone="ink3" numberOfLines={2}>
                          {m.catalyst}
                        </Txt>
                      ) : null}
                    </View>
                    <Txt
                      variant="cardTitle"
                      tone={(m.change_pct ?? 0) >= 0 ? 'gain' : 'loss'}
                      tabular
                    >
                      {fmtSignedPct(m.change_pct ?? null)}
                    </Txt>
                  </View>
                ))}
              </Card>
            ) : null}

            {data.picks?.map((pick, i) => (
              <PickCard key={pick.ticker} pick={pick} rank={i + 1} />
            ))}

            <Txt variant="caption" tone="ink3" center style={styles.gap}>
              {data.disclaimer ?? 'Informational only. Not investment advice.'}
            </Txt>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

function PickCard({ pick, rank }: { pick: Pick; rank: number }) {
  const router = useRouter();
  const quantOnly = pick.analysis !== 'ok';
  const v = pick.verification;
  const confidence = pick.confidence == null ? null : Math.round(pick.confidence * 100);

  return (
    <Card>
      <Pressable
        onPress={() => router.push(`/stock/${pick.ticker}`)}
        accessibilityRole="button"
        accessibilityLabel={`${pick.ticker}, rank ${rank}`}
      >
        <View style={styles.pickTop}>
          <Txt variant="caption" tone="ink3">
            #{rank}
          </Txt>
          <Txt variant="heading" tone="ink">
            {pick.ticker}
          </Txt>
          {pick.demoted ? <Tag label="Demoted" tone="warn" /> : null}
          <View style={styles.spacer} />
          {confidence != null ? (
            <Txt variant="caption" tone="ink3" tabular>
              {confidence}
            </Txt>
          ) : null}
        </View>
        {pick.name ? (
          <Txt variant="caption" tone="ink3" numberOfLines={1}>
            {pick.name}
            {pick.industry ? ` · ${pick.industry}` : ''}
          </Txt>
        ) : null}
      </Pressable>

      {pick.demoted ? (
        <Txt variant="caption" tone="warn" style={styles.gap}>
          The verifier challenged parts of this analysis; ranked down and shown for
          transparency.
        </Txt>
      ) : null}

      {quantOnly ? (
        <Txt variant="caption" tone="ink3" style={styles.gap}>
          Quantitative scores only: the analyst stage was unavailable for this name.
        </Txt>
      ) : (
        <>
          {pick.thesis ? (
            <Txt variant="bodySm" tone="ink2" style={styles.gap}>
              {pick.thesis}
            </Txt>
          ) : null}
          {pick.why_now ? (
            <Txt variant="caption" tone="ink2" style={styles.gap}>
              <Txt variant="caption" tone="ink" style={styles.bold}>
                Why now:{' '}
              </Txt>
              {pick.why_now}
            </Txt>
          ) : null}

          {/* The evidence table is the product's whole claim — a model opinion
              with nothing under it is what this app exists not to be. */}
          {pick.valuation_evidence?.length ? (
            <View style={styles.evidence}>
              <View style={styles.evRow}>
                <Txt variant="label" tone="ink3" uppercase style={styles.evMetric}>
                  metric
                </Txt>
                <Txt variant="label" tone="ink3" uppercase style={styles.evCol}>
                  this
                </Txt>
                <Txt variant="label" tone="ink3" uppercase style={styles.evCol}>
                  peers
                </Txt>
              </View>
              {pick.valuation_evidence.slice(0, 5).map((e) => (
                <View key={e.metric} style={styles.evRow}>
                  <Txt variant="caption" tone="ink" style={styles.evMetric}>
                    {e.metric.replaceAll('_', ' ')}
                  </Txt>
                  <Txt variant="caption" tone="ink2" tabular style={styles.evCol}>
                    {String(e.value ?? '–')}
                  </Txt>
                  <Txt variant="caption" tone="ink2" tabular style={styles.evCol}>
                    {String(e.sector_median ?? '–')}
                  </Txt>
                </View>
              ))}
            </View>
          ) : null}

          {pick.risks?.length ? (
            <View style={styles.gap}>
              {pick.risks.slice(0, 3).map((r, i) => (
                <Txt key={i} variant="caption" tone="ink2">
                  · {r.text}
                </Txt>
              ))}
            </View>
          ) : null}
        </>
      )}

      <View style={styles.foot}>
        {v?.critic_ran ? (
          <Tag
            label={`${v.verified ?? 0}/${v.checked ?? 0} verified${
              v.challenged ? `, ${v.challenged} challenged` : ''
            }`}
            tone={v.challenged ? 'warn' : 'gain'}
          />
        ) : (
          <Tag label="Unverified" tone="neutral" />
        )}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.s4,
    paddingVertical: space.s2,
  },
  navSpacer: { width: 56 },
  content: { paddingHorizontal: space.s4, paddingBottom: space.s9 },
  gap: { marginTop: space.s2 },
  bold: { fontWeight: '700' },
  spacer: { flex: 1 },
  pickTop: { flexDirection: 'row', alignItems: 'center', gap: space.s2 },
  mover: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.s3,
    paddingVertical: space.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.line,
  },
  moverMain: { flex: 1 },
  evidence: {
    marginTop: space.s2,
    borderRadius: radius.s,
  },
  evRow: {
    flexDirection: 'row',
    paddingVertical: space.s1,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.line,
  },
  evMetric: { flex: 2 },
  evCol: { flex: 1, textAlign: 'right' },
  foot: { flexDirection: 'row', marginTop: space.s2 },
});
