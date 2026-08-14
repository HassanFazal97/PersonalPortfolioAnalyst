import { useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useDashboard } from '@/api/bootstrap';
import type { NewsItem } from '@/api/types';
import { dayLabel } from '@/format';
import { space } from '@/theme/tokens';
import {
  Card,
  EmptyState,
  ErrorNote,
  Screen,
  SegmentedTabs,
  SkeletonBlock,
  Tag,
  Txt,
  type TagTone,
} from '@/ui';

type Filter = 'all' | 'digest' | 'alert' | 'holding';

const FILTERS = [
  { key: 'all' as const, label: 'All' },
  { key: 'digest' as const, label: 'Digests' },
  { key: 'alert' as const, label: 'Alerts' },
  { key: 'holding' as const, label: 'Holding news' },
];

const SEVERITY_TONE: Record<string, TagTone> = {
  high: 'loss',
  medium: 'warn',
  low: 'neutral',
};

export default function NewsTab() {
  const { data, isFetching, refetch } = useDashboard();
  const [filter, setFilter] = useState<Filter>('all');

  const section = data?.sections.news;
  const items = useMemo(() => {
    const all = section?.value?.items ?? [];
    return filter === 'all' ? all : all.filter((i) => i.kind === filter);
  }, [section?.value?.items, filter]);

  return (
    <Screen
      title="News"
      subtitle="Digests, alerts, and holding news"
      onRefresh={() => void refetch()}
      refreshing={isFetching}
      sticky={<SegmentedTabs items={FILTERS} value={filter} onChange={setFilter} />}
    >
      {section?.error && !section.value ? (
        <ErrorNote message="The news feed could not be loaded." onRetry={() => void refetch()} />
      ) : null}

      {!data ? (
        <Card>
          <SkeletonBlock lines={4} />
        </Card>
      ) : null}

      {items.map((item, i) => (
        <NewsCard key={item.id ?? i} item={item} />
      ))}

      {data && !items.length ? (
        <EmptyState
          title={filter === 'all' ? 'Nothing yet' : 'Nothing in this filter'}
          body={
            filter === 'all'
              ? 'Digests, alerts, and articles about your holdings land here once Cirvia surfaces them.'
              : 'Try another filter.'
          }
        />
      ) : null}
    </Screen>
  );
}

function NewsCard({ item }: { item: NewsItem }) {
  const when = dayLabel(item.published_at ?? item.created_at);
  const severity = item.severity?.toLowerCase();

  return (
    <Card>
      <View style={styles.meta}>
        {severity ? (
          <Tag label={severity} tone={SEVERITY_TONE[severity] ?? 'neutral'} />
        ) : null}
        {item.ticker ? <Tag label={item.ticker} tone="neutral" /> : null}
        {item.category ? (
          <Tag label={item.category.replaceAll('_', ' ')} tone="neutral" />
        ) : null}
        <View style={styles.spacer} />
        <Txt variant="caption" tone="ink3">
          {when}
        </Txt>
      </View>
      {item.title ? (
        <Txt variant="cardTitle" tone="ink" style={styles.title}>
          {item.title}
        </Txt>
      ) : null}
      {item.body ? (
        <Txt variant="bodySm" tone="ink2" numberOfLines={6}>
          {item.body}
        </Txt>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  meta: { flexDirection: 'row', alignItems: 'center', gap: space.s1, marginBottom: space.s1 },
  spacer: { flex: 1 },
  title: { marginBottom: space.s1 },
});
