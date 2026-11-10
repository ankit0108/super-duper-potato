import { describe, expect, it } from "vitest";
import type { Card, DeskState } from "@/types";
import { applyEvents } from "./overlay";
import { addDays, isDue, nextMonday, saveChoices, savedLabel } from "./save";
import { boardSections, todaySets } from "@/state/selectors";

const card = (over: Partial<Card>): Card => ({ id: "c1", platform: "linkedin", status: "suggested", kind: "news", format: "li_text", title: "T", created_at: "2026-11-09T19:00:00Z", delivery_id: "dly_2026-11-10", ...over }) as Card;
const today = "2026-11-10"; // a Tuesday

describe("save for later", () => {
  it("offers tomorrow, three days on and next Monday", () => {
    expect(addDays("2026-12-30", 3)).toBe("2027-01-02");
    expect(nextMonday(today)).toBe("2026-11-16");
    expect(nextMonday("2026-11-16")).toBe("2026-11-23"); // on a Monday: the one after
    expect(saveChoices(today).map((c) => c.day)).toEqual([null, "2026-11-11", "2026-11-13", "2026-11-16"]);
  });

  it("keeps a saved card out of today's picks until its day, then puts it first", () => {
    const plain = card({ id: "a", rank: 1 });
    const later = card({ id: "b", rank: 2, saved: { at: "2026-11-10T01:00:00Z", remind_on: "2026-11-12", reminded: false } });
    const noDay = card({ id: "c", rank: 3, saved: { at: "2026-11-10T02:00:00Z", remind_on: null, reminded: false } });
    const due = card({ id: "d", delivery_id: "dly_2026-11-05", saved: { at: "2026-11-05T02:00:00Z", remind_on: today, reminded: false } });
    const view = { cards: [plain, later, noDay, due] } as unknown as DeskState;
    const s = boardSections(view, today, "UTC", "all");
    expect(s.today.linkedin.map((c) => c.id)).toEqual(["d", "a"]);
    expect(s.saved.map((c) => c.id)).toEqual(["b", "c"]); // the one with a day first
    expect(todaySets(s.today.linkedin, today).map((x) => x.kind)).toEqual(["saved", "morning"]);
    expect(isDue(due, today)).toBe(true);
    expect(savedLabel(due, today)).toBe("Saved for today");
    expect(savedLabel(later, today)).toBe("Saved for Thu 12 Nov");
    expect(savedLabel(noDay, today)).toBe("Saved");
  });

  it("shows a save at once, brings an expired card back, and a skip ends it", () => {
    const desk = { cards: [card({ id: "x", status: "expired", expires_at: "2026-11-09T00:00:00Z" })] } as unknown as DeskState;
    let n = 0;
    const ev = (type: string, extra: object) => ({ id: `e${++n}`, at: "2026-11-10T03:00:00Z", type, ...extra }) as never;
    const saved = applyEvents(desk, [ev("card.save", { card_id: "x", saved: true, remind_on: "2026-11-12" })]).desk.cards![0];
    expect(saved.status).toBe("suggested");
    expect(saved.saved?.remind_on).toBe("2026-11-12");
    expect(saved.expires_at).toBeNull();
    const out = applyEvents(desk, [ev("card.save", { card_id: "x", saved: true, remind_on: null }), ev("card.skip", { card_id: "x", reason: "wrong_timing" })]).desk.cards![0];
    expect(out.status).toBe("skipped");
    expect(out.saved).toBeNull();
    const removed = applyEvents(desk, [ev("card.save", { card_id: "x", saved: true, remind_on: null }), ev("card.save", { card_id: "x", saved: false, remind_on: null })]).desk.cards![0];
    expect(removed.saved).toBeNull();
  });
});
