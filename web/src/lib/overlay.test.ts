import { card, desk, event } from "@/test/fixtures";
import { applyEvents, deepMerge } from "./overlay";

describe("applyEvents", () => {
  it("returns the same state when nothing is pending", () => {
    const d = desk({ cards: [card()] });
    expect(applyEvents(d, []).desk).toBe(d);
  });

  it("an edit moves a suggested card to editing and keeps the working copy", () => {
    const c = card();
    const { desk: out, pending } = applyEvents(desk({ cards: [c] }), [event("card.edit", { card_id: c.id, text: "Edited." })]);
    const next = out.cards!.find((x) => x.id === c.id)!;
    expect(next.status).toBe("editing");
    expect(next.working?.text).toBe("Edited.");
    expect(pending.cards.has(c.id)).toBe(true);
  });

  it("posting creates a pending post with the edit ratio against the draft", () => {
    const c = card({ draft: { text: "one two three four", posts: [] } });
    const { desk: out, pending } = applyEvents(desk({ cards: [c] }), [event("card.posted", { card_id: c.id, text: "one two three five" })]);
    const post = out.posts![0];
    expect(post.card_id).toBe(c.id);
    expect(post.final_text).toBe("one two three five");
    expect(post.edit_ratio).toBeCloseTo(0.25, 4);
    expect(out.cards!.find((x) => x.id === c.id)!.status).toBe("posted");
    expect(pending.posts.has(post.id)).toBe(true);
  });

  it("a thread posts its posts, joined", () => {
    const c = card({ platform: "x", format: "x_thread", draft: { text: "", posts: ["a", "b"] } });
    const { desk: out } = applyEvents(desk({ cards: [c] }), [event("card.posted", { card_id: c.id, posts: ["a!", "b"] })]);
    expect(out.posts![0].final_text).toBe("a!\n\nb");
    expect(out.posts![0].final_posts).toEqual(["a!", "b"]);
  });

  it("skipping records the reason and clears pending work", () => {
    const c = card({ work: { kind: "rewrite" } });
    const { desk: out } = applyEvents(desk({ cards: [c] }), [event("card.skip", { card_id: c.id, reason: "off_brand" })]);
    const next = out.cards!.find((x) => x.id === c.id)!;
    expect(next.status).toBe("skipped");
    expect(next.skip?.reason).toBe("off_brand");
    expect(next.work).toBeNull();
  });

  it("events for unknown cards are ignored, not thrown", () => {
    const d = desk({ cards: [card()] });
    expect(() => applyEvents(d, [event("card.skip", { card_id: "nope", reason: "other" })])).not.toThrow();
  });

  it("does not mutate the input", () => {
    const c = card();
    const d = desk({ cards: [c] });
    applyEvents(d, [event("card.status", { card_id: c.id, status: "editing" })]);
    expect(d.cards![0].status).toBe("suggested");
  });
});

describe("deepMerge", () => {
  it("merges nested objects, replaces arrays, and null deletes", () => {
    const base = { a: { b: 1, c: 2 }, list: [1, 2], gone: 1 };
    expect(deepMerge(base, { a: { c: 3 }, list: [9], gone: null })).toEqual({ a: { b: 1, c: 3 }, list: [9] });
  });
});
