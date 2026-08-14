import { useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useDashboard } from '@/api/bootstrap';
import { useChatRun } from '@/chat/useChatRun';
import type { ChatMessage } from '@/chat/types';
import { color, radius, space, type, HIT_SLOP } from '@/theme/tokens';
import { Banner, Txt } from '@/ui';

export default function ChatModal() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { messages, busy, send } = useChatRun();
  const [draft, setDraft] = useState('');
  const scrollRef = useRef<ScrollView>(null);

  const { data } = useDashboard();
  const quota = data?.sections.me.value?.chat_quota;
  const recovered = messages.some((m) => m.recovered);

  useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [messages]);

  const submit = () => {
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    void send(text);
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={insets.top}
    >
      <View style={styles.header}>
        <View style={styles.headerSide} />
        <Txt variant="heading" tone="ink">
          Ask Cirvia
        </Txt>
        <Pressable
          onPress={() => router.back()}
          hitSlop={HIT_SLOP}
          accessibilityRole="button"
          accessibilityLabel="Close"
          style={styles.headerSide}
        >
          <Txt variant="body" tone="accent" style={styles.close}>
            Close
          </Txt>
        </Pressable>
      </View>

      <ScrollView
        ref={scrollRef}
        style={styles.log}
        contentContainerStyle={styles.logContent}
        keyboardShouldPersistTaps="handled"
      >
        {recovered ? (
          <Banner
            tone="setup"
            title="Picked up where you left off."
            body="This answer finished while the app was closed."
          />
        ) : null}

        {messages.length === 0 ? (
          <View style={styles.intro}>
            <Txt variant="bodySm" tone="ink3" center>
              Ask about your holdings, your digest, or a stock you follow. Cirvia answers
              from your actual portfolio.
            </Txt>
          </View>
        ) : null}

        {messages.map((message) => (
          <Bubble key={message.id} message={message} />
        ))}
      </ScrollView>

      <View style={[styles.composer, { paddingBottom: insets.bottom + space.s2 }]}>
        <View style={styles.row}>
          <TextInput
            style={styles.input}
            value={draft}
            onChangeText={setDraft}
            placeholder="Any news on my holdings today?"
            placeholderTextColor={color.ink3}
            selectionColor={color.accent}
            maxLength={500}
            multiline
            returnKeyType="send"
            onSubmitEditing={submit}
            accessibilityLabel="Your question"
          />
          <Pressable
            onPress={submit}
            disabled={busy || !draft.trim()}
            accessibilityRole="button"
            accessibilityLabel="Send"
            accessibilityState={{ disabled: busy || !draft.trim(), busy }}
            style={[styles.send, (busy || !draft.trim()) && styles.sendOff]}
          >
            <Txt variant="body" tone="inverse">
              ↑
            </Txt>
          </Pressable>
        </View>
        <Txt variant="caption" tone="ink3" center style={styles.footnote}>
          {quota?.remaining != null ? `${quota.remaining} questions left. ` : ''}
          Informational only. Cirvia never gives buy or sell advice.
        </Txt>
      </View>
    </KeyboardAvoidingView>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const mine = message.role === 'user';
  return (
    <View style={[styles.bubble, mine ? styles.mine : styles.theirs]}>
      <Txt variant="bodySm" tone={message.error ? 'loss' : mine ? 'ink' : 'ink2'}>
        {message.text}
        {message.pending && !message.text ? 'Thinking…' : ''}
      </Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.s4,
    paddingVertical: space.s3,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.line,
  },
  headerSide: { minWidth: 56 },
  close: { textAlign: 'right', fontWeight: '600' },
  log: { flex: 1 },
  logContent: { padding: space.s4, gap: space.s2 },
  intro: { paddingVertical: space.s7 },
  bubble: {
    maxWidth: '82%',
    paddingHorizontal: space.s3,
    paddingVertical: space.s2,
    borderRadius: radius.l,
  },
  mine: {
    alignSelf: 'flex-end',
    backgroundColor: color.surface3,
    borderBottomRightRadius: radius.s / 2,
  },
  theirs: {
    alignSelf: 'flex-start',
    backgroundColor: color.accentWash,
    borderBottomLeftRadius: radius.s / 2,
  },
  composer: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.line,
    backgroundColor: color.surface1,
    paddingHorizontal: space.s4,
    paddingTop: space.s3,
    gap: space.s2,
  },
  row: { flexDirection: 'row', alignItems: 'flex-end', gap: space.s2 },
  input: {
    flex: 1,
    maxHeight: 120,
    backgroundColor: color.surface2,
    borderWidth: 1,
    borderColor: color.lineStrong,
    borderRadius: radius.xl,
    paddingHorizontal: space.s4,
    paddingVertical: space.s2,
    fontSize: type.bodySm.fontSize,
    color: color.ink,
  },
  send: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: color.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendOff: { opacity: 0.45 },
  footnote: {},
});
