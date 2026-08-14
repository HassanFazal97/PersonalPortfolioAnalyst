import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import EventSource, { type EventSourceListener } from 'react-native-sse';

import { accessTokenForStream, ApiError, api } from '@/api/client';
import { prefs } from '@/api/storage';
import { API_BASE } from '@/config';
import type { ChatEvent, ChatMessage, ChatSnapshot, RunDetail } from '@/chat/types';

/**
 * One chat turn, driven by the `/chat/start` + run-events pair.
 *
 * The shape of this hook is dictated by one fact: iOS suspends the app and
 * kills the socket, but the run keeps going server-side and is billed either
 * way. So the run id is persisted the moment it is known, and re-subscribed
 * on foreground — the answer is recovered rather than lost.
 */

const PENDING_KEY = 'chat:pending-run';

type PendingRun = { runId: string; question: string; startedAt: number };

/** A run older than this is not worth reattaching to; the agent budget is far under it. */
const PENDING_TTL_MS = 10 * 60 * 1000;

function readPending(): PendingRun | null {
  const raw = prefs.getString(PENDING_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as PendingRun;
    if (Date.now() - parsed.startedAt > PENDING_TTL_MS) {
      prefs.remove(PENDING_KEY);
      return null;
    }
    return parsed;
  } catch {
    prefs.remove(PENDING_KEY);
    return null;
  }
}

export type ChatState = {
  messages: ChatMessage[];
  busy: boolean;
  error: string | null;
  send: (message: string) => Promise<void>;
};

export function useChatRun(): ChatState {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);
  const deltasRef = useRef('');

  const closeSource = useCallback(() => {
    sourceRef.current?.removeAllEventListeners();
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  /** Fold one event into the visible transcript. */
  const apply = useCallback((event: ChatEvent, opts: { recovered?: boolean } = {}) => {
    if (event.type === 'text_delta' && typeof event.text === 'string') {
      deltasRef.current += event.text;
      const text = deltasRef.current;
      setMessages((prev) => replacePending(prev, { text, pending: true }));
      return;
    }
    if (event.type === 'done') {
      // `done.answer` is authoritative: deltas can be dropped under queue
      // pressure, so the accumulated text is discarded in its favour.
      const answer = typeof event.answer === 'string' ? event.answer : deltasRef.current;
      setMessages((prev) =>
        replacePending(prev, { text: answer, pending: false, recovered: opts.recovered }),
      );
      deltasRef.current = '';
      setBusy(false);
      prefs.remove(PENDING_KEY);
      return;
    }
    if (event.type === 'error') {
      const detail =
        typeof event.detail === 'string'
          ? event.detail
          : 'Something went wrong answering that.';
      setMessages((prev) => replacePending(prev, { text: detail, pending: false, error: true }));
      deltasRef.current = '';
      setBusy(false);
      prefs.remove(PENDING_KEY);
    }
  }, []);

  /**
   * Last resort when the SSE cannot be opened at all: the run row itself
   * carries the finished answer.
   */
  const collectFromRun = useCallback(
    async (runId: string) => {
      try {
        const detail = await api<RunDetail>(`/runs/${runId}`);
        if (detail.run.final_answer) {
          apply(
            { type: 'done', run_id: runId, answer: detail.run.final_answer, status: detail.run.status },
            { recovered: true },
          );
          return true;
        }
      } catch {
        // 404 or offline — nothing recoverable.
      }
      return false;
    },
    [apply],
  );

  const subscribe = useCallback(
    async (runId: string, opts: { recovered?: boolean } = {}) => {
      closeSource();
      const token = await accessTokenForStream();
      if (!token) return;

      const source = new EventSource(`${API_BASE}/chat/runs/${runId}/events`, {
        headers: { Authorization: `Bearer ${token}` },
        // The server replays what was missed on every (re)connect, so the
        // library's own retry is safe to leave on.
        pollingInterval: 0,
      });
      sourceRef.current = source;

      const onMessage: EventSourceListener<string> = (event) => {
        if (event.type !== 'message' || !event.data) return;
        let parsed: ChatEvent | ChatSnapshot;
        try {
          parsed = JSON.parse(event.data) as ChatEvent | ChatSnapshot;
        } catch {
          return;
        }
        if (parsed.type === 'chat_snapshot') {
          const snapshot = parsed as ChatSnapshot;
          // Replay is idempotent: deltas are re-accumulated from zero and a
          // `done` inside the snapshot overwrites them anyway.
          deltasRef.current = '';
          for (const replayed of snapshot.events) {
            apply(replayed, { recovered: opts.recovered });
          }
          if (snapshot.finished) {
            closeSource();
            // Finished with no terminal frame left in the buffer: fall back
            // to the persisted run.
            const hasTerminal = snapshot.events.some(
              (e) => e.type === 'done' || e.type === 'error',
            );
            if (!hasTerminal) void collectFromRun(runId);
          }
          return;
        }
        apply(parsed as ChatEvent, { recovered: opts.recovered });
        if (parsed.type === 'done' || parsed.type === 'error') closeSource();
      };

      // The framing puts the event name in `event:`, so every frame arrives
      // under its own type as well as the generic one.
      source.addEventListener('message', onMessage);
      for (const name of ['chat_snapshot', 'run_start', 'tool_start', 'tool_end', 'text_delta', 'done', 'error'] as const) {
        source.addEventListener(name as 'message', onMessage);
      }
      source.addEventListener('error', () => {
        // Transport failure. The run is still going server-side; the pending
        // record means foregrounding will try again.
        void collectFromRun(runId);
      });
    },
    [apply, closeSource, collectFromRun],
  );

  const send = useCallback(
    async (message: string) => {
      const text = message.trim();
      if (!text || busy) return;
      setError(null);
      setBusy(true);
      deltasRef.current = '';
      setMessages((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, role: 'user', text },
        { id: `a-${Date.now()}`, role: 'assistant', text: '', pending: true },
      ]);

      try {
        const { run_id } = await api<{ run_id: string }>('/chat/start', {
          method: 'POST',
          body: { message: text },
        });
        // Persisted before the socket is opened: if the app is killed in the
        // next second, the answer is still recoverable.
        prefs.set(
          PENDING_KEY,
          JSON.stringify({ runId: run_id, question: text, startedAt: Date.now() }),
        );
        await subscribe(run_id);
      } catch (e) {
        const detail =
          e instanceof ApiError ? e.detail : 'Could not reach Cirvia. Try again.';
        setMessages((prev) => replacePending(prev, { text: detail, pending: false, error: true }));
        setError(detail);
        setBusy(false);
      }
    },
    [busy, subscribe],
  );

  // Reattach on mount and on every foreground: this is the whole point of the
  // run-id-first design.
  useEffect(() => {
    const reattach = () => {
      const pending = readPending();
      if (!pending || sourceRef.current) return;
      setBusy(true);
      setMessages((prev) =>
        prev.length
          ? prev
          : [
              { id: `u-${pending.runId}`, role: 'user', text: pending.question },
              { id: `a-${pending.runId}`, role: 'assistant', text: '', pending: true },
            ],
      );
      void subscribe(pending.runId, { recovered: true });
    };

    reattach();
    const onAppState = (state: AppStateStatus) => {
      if (state === 'active') reattach();
      else closeSource();
    };
    const sub = AppState.addEventListener('change', onAppState);
    return () => {
      sub.remove();
      closeSource();
    };
  }, [subscribe, closeSource]);

  return { messages, busy, error, send };
}

/** Rewrite the trailing assistant bubble, which is the only one in flight. */
function replacePending(
  messages: ChatMessage[],
  patch: Partial<ChatMessage> & { text: string },
): ChatMessage[] {
  const index = messages.findLastIndex((m) => m.role === 'assistant');
  if (index < 0) {
    return [...messages, { id: `a-${Date.now()}`, role: 'assistant', ...patch }];
  }
  const next = [...messages];
  next[index] = { ...next[index]!, ...patch };
  return next;
}
