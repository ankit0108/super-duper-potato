// The outbox: desk actions become events, persisted locally, written to inbox/ in batches, and kept as an
// overlay until desk.json says the pipeline applied (or rejected) them.
import type { DeskState, EventInput, InboxEvent } from "@/types";
import { newId } from "./storage";

export type OutboxState = "pending" | "sending" | "sent" | "failed";

export type OutboxItem = {
  event: InboxEvent;
  state: OutboxState;
  needsRun: boolean;
  batch?: string;
  sentAt?: string;
  error?: string;
  attempts?: number;
};

/**
 * Whether the desk starts a pipeline run after sending each kind of event: yes for anything he waits on (a draft,
 * a rewrite, a cross-post, a visual, a request), no for bookkeeping the next run picks up. Every event type must be
 * listed, so a new one can't silently wait hours for the schedule (cross-posts and visuals once did).
 */
export const STARTS_RUN: Record<InboxEvent["type"], boolean> = {
  "card.status": false,
  "card.edit": false,
  "card.posted": false,
  "card.skip": false,
  "card.rewrite": true,
  "card.crosspost": true,
  "card.visual": true,
  "card.answers": true,
  "card.restore": false,
  "card.draft_now": true,
  "card.hook": false,
  "post.update": false,
  "post.metrics": false,
  "metrics.upload": true,
  "metrics.review": false,
  "account.stats": false,
  "request.create": true,
  "request.cancel": false,
  "stance.upsert": false,
  "stance.delete": false,
  "stance.propose": true,
  "source.upsert": false,
  "source.delete": false,
  "settings.update": false,
  "profile.update": false,
  "proposal.decide": false,
  "playbook.rule": false,
  "run.request": true,
};

export function makeEvent(input: EventInput, now: Date = new Date()): InboxEvent {
  return { ...input, id: newId("ev"), at: now.toISOString().replace(/\.\d{3}Z$/, "Z") } as InboxEvent;
}

export function toItem(event: InboxEvent): OutboxItem {
  return { event, state: "pending", needsRun: STARTS_RUN[event.type] ?? true };
}

export function buildBatch(events: InboxEvent[], device: string, now: Date = new Date()) {
  const id = newId("evb");
  const stamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const safeDevice = device.replace(/[^a-z0-9-]/gi, "").slice(0, 16) || "desk";
  const path = `inbox/${stamp}_${safeDevice}_${id.slice(-8)}.json`;
  const body = { v: 1, id, device: safeDevice, created_at: now.toISOString().replace(/\.\d{3}Z$/, "Z"), events };
  return { path, body };
}

export type Reconciled = {
  items: OutboxItem[];
  applied: string[];
  rejected: Array<{ item: OutboxItem; error: string }>;
};

/** Drop events the pipeline has processed; surface the ones it rejected. */
export function reconcile(items: OutboxItem[], desk: DeskState | null, now: Date = new Date()): Reconciled {
  if (!desk) return { items, applied: [], rejected: [] };
  const processed = new Set(desk.processed_event_ids ?? []);
  const rejectedById = new Map((desk.rejected_events ?? []).map((r) => [r.id, r.error ?? "rejected"]));
  const keep: OutboxItem[] = [];
  const applied: string[] = [];
  const rejected: Array<{ item: OutboxItem; error: string }> = [];
  const staleBefore = now.getTime() - 3 * 86400_000;
  for (const item of items) {
    const id = item.event.id;
    if (rejectedById.has(id)) {
      rejected.push({ item, error: rejectedById.get(id)! });
    } else if (processed.has(id)) {
      applied.push(id);
    } else if (item.state === "sent" && item.sentAt && new Date(item.sentAt).getTime() < staleBefore) {
      // The pipeline keeps 7 days of processed ids; anything older than 3 days is long done.
      applied.push(id);
    } else {
      keep.push(item);
    }
  }
  return { items: keep, applied, rejected };
}

export function pendingEvents(items: OutboxItem[]): InboxEvent[] {
  return items.map((i) => i.event);
}
