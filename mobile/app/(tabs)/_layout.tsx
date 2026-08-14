import { Redirect, Tabs } from 'expo-router';
import { StyleSheet } from 'react-native';

import { useSession } from '@/auth/session';
import { color, type } from '@/theme/tokens';
import { DigestIcon, HoldingsIcon, NewsIcon, WatchingIcon } from '@/ui/icons';

export default function TabsLayout() {
  const { session } = useSession();
  if (!session) return <Redirect href="/(auth)/sign-in" />;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: color.accentText,
        tabBarInactiveTintColor: color.ink3,
        tabBarStyle: styles.bar,
        tabBarLabelStyle: styles.label,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Digest',
          tabBarIcon: ({ color: c }) => <DigestIcon color={c} />,
        }}
      />
      <Tabs.Screen
        name="news"
        options={{
          title: 'News',
          tabBarIcon: ({ color: c }) => <NewsIcon color={c} />,
        }}
      />
      <Tabs.Screen
        name="holdings"
        options={{
          title: 'Holdings',
          tabBarIcon: ({ color: c }) => <HoldingsIcon color={c} />,
        }}
      />
      <Tabs.Screen
        name="watching"
        options={{
          title: 'Watching',
          tabBarIcon: ({ color: c }) => <WatchingIcon color={c} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: color.surface1,
    borderTopColor: color.line,
  },
  label: {
    fontSize: type.label.fontSize,
    fontWeight: '600',
  },
});
