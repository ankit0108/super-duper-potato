// Small builders for unit tests: only the fields a test cares about, typed against the real contract.
import type { Card, DeskState, InboxEvent } from "@/types";

let n = 0;

export function card(over: Partial<Card> = {}): Card {
  n += 1;
  return {
    id: `crd_${n}`,
    platform: "linkedin",
    pillar: "research",
    format: "li_text",
    title: `Card ${n}`,
    status: "suggested",
    created_at: "2026-09-28T19:43:00Z",
    draft: { text: "The draft text.", posts: [] },
    ...over,
  } as Card;
}

export function desk(over: Partial<DeskState> = {}): DeskState {
  return {
    meta: { schema_version: 1, generated_at: "2026-09-28T20:31:00Z", timezone: "Australia/Melbourne" },
    cards: [],
    posts: [],
    requests: [],
    stances: [],
    sources: [],
    proposals: [],
    metrics: [],
    uploads: [],
    account_stats: [],
    processed_event_ids: [],
    rejected_events: [],
    ...over,
  } as DeskState;
}

export function event<T extends InboxEvent["type"]>(type: T, fields: Omit<Extract<InboxEvent, { type: T }>, "id" | "at" | "type">, id = `ev_${++n}`): InboxEvent {
  return { id, at: "2026-09-28T21:00:00Z", type, ...fields } as InboxEvent;
}
