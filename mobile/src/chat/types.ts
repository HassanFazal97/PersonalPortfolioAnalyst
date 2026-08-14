import type { ChatQuota } from '@/api/types';

/** Events the agent loop emits, as they arrive over SSE. */
export type ChatEvent =
  | { type: 'run_start'; run_id: string }
  | { type: 'tool_start'; name: string; label?: string; input_summary?: string }
  | { type: 'tool_end'; name: string; ok: boolean; latency_ms?: number }
  | { type: 'text_delta'; text: string }
  | { type: 'done'; run_id: string; answer: string; status: string; chat_quota?: ChatQuota }
  | { type: 'error'; detail: string }
  | { type: string; [key: string]: unknown };

/**
 * Opening frame of `GET /chat/runs/{id}/events`: everything published for the
 * run so far, plus whether it is over. A client that was suspended for the
 * whole run gets its answer from here alone.
 */
export type ChatSnapshot = {
  type: 'chat_snapshot';
  run_id: string;
  finished: boolean;
  events: ChatEvent[];
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  /** Streaming in right now — the caret renders on this one. */
  pending?: boolean;
  error?: boolean;
  /** Recovered from a run that finished while the app was backgrounded. */
  recovered?: boolean;
};

export type RunDetail = {
  run: {
    id: string;
    final_answer: string | null;
    status: string;
    user_message: string;
  };
};
