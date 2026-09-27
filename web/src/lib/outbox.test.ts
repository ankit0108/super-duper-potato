import { desk } from "@/test/fixtures";
import { buildBatch, makeEvent, reconcile, toItem } from "./outbox";

const now = new Date("2026-09-28T21:00:00.123Z");

describe("outbox", () => {
  it("stamps events with an id and a second-precision time", () => {
    const ev = makeEvent({ type: "card.skip", card_id: "c1", reason: "other" }, now);
    expect(ev.id).toMatch(/^ev_/);
    expect(ev.at).toBe("2026-09-28T21:00:00Z");
  });

  it("marks events that need a pipeline run", () => {
    expect(toItem(makeEvent({ type: "card.rewrite", card_id: "c1", note: "", chips: [] }, now)).needsRun).toBe(true);
    expect(toItem(makeEvent({ type: "card.edit", card_id: "c1", text: "x" }, now)).needsRun).toBe(false);
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
