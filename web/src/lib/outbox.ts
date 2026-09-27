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

/** Events the pipeline should act on promptly (the desk starts a run after sending them). */
const RUN_TYPES = new Set<InboxEvent["type"]>([
  "card.answers",
  "card.rewrite",
  "card.draft_now",
  "request.create",
  "stance.propose",
  "metrics.upload",
  "run.request",
]);

export function makeEvent(input: EventInput, now: Date = new Date()): InboxEvent {
  return { ...input, id: newId("ev"), at: now.toISOString().replace(/\.\d{3}Z$/, "Z") } as InboxEvent;
}

export function toItem(event: InboxEvent): OutboxItem {
  return { event, state: "pending", needsRun: RUN_TYPES.has(event.type) };
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
