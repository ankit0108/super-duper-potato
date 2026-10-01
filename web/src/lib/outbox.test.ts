import type { InboxEvent } from "@/types";
import { card, desk, event } from "@/test/fixtures";
import { applyEvents } from "./overlay";
import { STARTS_RUN, buildBatch, makeEvent, reconcile, toItem } from "./outbox";

const now = new Date("2026-09-28T21:00:00.123Z");

describe("outbox", () => {
  it("stamps events with an id and a second-precision time", () => {
    const ev = makeEvent({ type: "card.skip", card_id: "c1", reason: "other" }, now);
    expect(ev.id).toMatch(/^ev_/);
    expect(ev.at).toBe("2026-09-28T21:00:00Z");
  });

  it("marks events that need a pipeline run", () => {
    expect(toItem(makeEvent({ type: "card.rewrite", card_id: "c1", note: "", chips: [] }, now)).needsRun).toBe(true);
    expect(toItem(makeEvent({ type: "card.crosspost", card_id: "c1", target_platform: "x", mode: "both", note: "" }, now)).needsRun).toBe(true);
    expect(toItem(makeEvent({ type: "card.visual", card_id: "c1", kind: "auto", note: "" }, now)).needsRun).toBe(true);
    expect(toItem(makeEvent({ type: "card.edit", card_id: "c1", text: "x" }, now)).needsRun).toBe(false);
  });

  it("starts a run for every card action that leaves the card waiting on the pipeline", () => {
    // One of each card event. Whatever leaves `work` on the card is something he waits for, so it must start a
    // run instead of sitting in inbox/ until the next schedule.
    const samples: InboxEvent[] = [
      event("card.status", { card_id: "c1", status: "editing" }),
      event("card.edit", { card_id: "c1", text: "New text" }),
      event("card.posted", { card_id: "c1" }),
      event("card.skip", { card_id: "c1", reason: "other", note: "Not my focus" }),
      event("card.rewrite", { card_id: "c1", note: "Shorter", chips: [] }),
      event("card.crosspost", { card_id: "c1", target_platform: "x", mode: "both", note: "" }),
      event("card.crosspost", { card_id: "c1", target_platform: "x", mode: "switch", note: "" }),
      event("card.visual", { card_id: "c1", kind: "auto", note: "" }),
      event("card.answers", { card_id: "c1", answers: [{ question_id: "q1", answer: "Because" }] }),
      event("card.restore", { card_id: "c1" }),
      event("card.draft_now", { card_id: "c1" }),
      event("card.hook", { card_id: "c1", hook_index: 0 }),
    ];
    const waiting: string[] = [];
    for (const ev of samples) {
      const c = card({ id: "c1", mode: "interview", questions: [{ id: "q1", q: "Why?" }], work: null });
      const { desk: out } = applyEvents(desk({ cards: [c] }), [ev]);
      if (out.cards![0].work) {
        waiting.push(ev.type);
        expect(toItem(ev).needsRun, `${ev.type} leaves the card waiting but starts no run`).toBe(true);
      }
    }
    expect(new Set(waiting)).toEqual(new Set(["card.rewrite", "card.crosspost", "card.visual", "card.answers", "card.draft_now"]));
    // Every event type is classified (the Record type enforces it; this guards the runtime map too).
    expect(Object.keys(STARTS_RUN)).toHaveLength(28);
  });

  it("writes batches under inbox/ with a safe device name", () => {
    const { path, body } = buildBatch([makeEvent({ type: "card.skip", card_id: "c1", reason: "other" }, now)], "Ankit's phone!", now);
    expect(path).toMatch(/^inbox\/20260928T210000Z_Ankitsphone_[\w-]{8}\.json$/);
    expect(body).toMatchObject({ v: 1, device: "Ankitsphone", created_at: "2026-09-28T21:00:00Z" });
    expect(body.events).toHaveLength(1);
  });

  it("reconciles against desk.json: applied, rejected with a reason, or still waiting", () => {
    const applied = { ...toItem(makeEvent({ type: "card.skip", card_id: "a", reason: "other" }, now)), state: "sent" as const };
    const rejected = { ...toItem(makeEvent({ type: "card.skip", card_id: "b", reason: "other" }, now)), state: "sent" as const };
    const waiting = { ...toItem(makeEvent({ type: "card.skip", card_id: "c", reason: "other" }, now)), state: "sent" as const, sentAt: now.toISOString() };
    const stale = { ...toItem(makeEvent({ type: "card.skip", card_id: "d", reason: "other" }, now)), state: "sent" as const, sentAt: "2026-09-20T00:00:00Z" };
    const d = desk({
      processed_event_ids: [applied.event.id, rejected.event.id],
      rejected_events: [{ id: rejected.event.id, type: "card.skip", error: "unknown card b", at: "2026-09-28T21:01:00Z" }],
    });
    const out = reconcile([applied, rejected, waiting, stale], d, now);
    expect(out.items.map((i) => i.event.id)).toEqual([waiting.event.id]);
    expect(out.applied).toEqual([applied.event.id, stale.event.id]);
    expect(out.rejected).toEqual([{ item: rejected, error: "unknown card b" }]);
  });
});
