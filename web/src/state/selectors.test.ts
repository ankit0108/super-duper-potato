import { card, desk } from "@/test/fixtures";
import { boardSections, todaySets } from "./selectors";

const today = "2026-09-29";
const tz = "Australia/Melbourne";

describe("boardSections", () => {
  const dly = `dly_${today}`;
  const cards = [
    card({ id: "t1", delivery_id: dly, rank: 2, status: "suggested" }),
    card({ id: "t2", delivery_id: dly, rank: 1, status: "editing" }),
    card({ id: "t3", delivery_id: dly, rank: 3, status: "needs_input", kind: "interview" }),
    card({ id: "t4", delivery_id: `${dly}_2`, rank: 1, status: "suggested" }),
    card({ id: "x1", delivery_id: dly, platform: "x", format: "x_single", rank: 1, status: "suggested" }),
    card({ id: "old-blocked", delivery_id: "dly_2026-09-28", status: "blocked" }),
    card({ id: "old-editing", delivery_id: "dly_2026-09-28", status: "editing", updated_at: "2026-09-28T10:00:00Z" }),
    card({ id: "wk-answer", delivery_id: "wkb_2026-W39", kind: "interview", status: "needs_input", created_at: "2026-09-26T09:00:00Z" }),
    card({ id: "req", kind: "request", status: "suggested", created_at: "2026-09-28T09:00:00Z" }),
    card({ id: "posted", delivery_id: dly, status: "posted", status_changed_at: "2026-09-28T21:00:00Z" }),
    card({ id: "expired", delivery_id: "dly_2026-09-27", status: "expired" }),
  ];
  const s = boardSections(desk({ cards }), today, tz, "all");

  it("keeps each of today's sets together in rank order, whatever each card's state, the newest set first", () => {
    expect(s.today.linkedin.map((c) => c.id)).toEqual(["t4", "t2", "t1", "t3"]);
    expect(s.today.x.map((c) => c.id)).toEqual(["x1"]);
    expect(todaySets(s.today.linkedin, today).map((set) => [set.kind, set.cards.map((c) => c.id)])).toEqual([
      ["fresh", ["t4"]],
      ["morning", ["t2", "t1", "t3"]],
    ]);
  });

  it("lists a cross-post he made today of an earlier card with today's picks, on top", () => {
    const xp = card({ id: "xp", platform: "x", format: "x_single", kind: "adapt", crosspost_of: "old-editing", delivery_id: "dly_2026-09-28", status: "suggested", created_at: "2026-09-28T23:30:00Z" });
    const out = boardSections(desk({ cards: [...cards, xp] }), today, tz, "all");
    expect(out.today.x.map((c) => c.id)).toEqual(["xp", "x1"]);
    expect(todaySets(out.today.x, today).map((set) => set.kind)).toEqual(["crossposts", "morning"]);
    expect(out.thisWeek.map((c) => c.id)).not.toContain("xp");
  });

  it("routes older cards by what they need", () => {
    expect(s.needsYou.map((c) => c.id)).toEqual(["old-blocked"]);
    expect(s.inProgress.map((c) => c.id)).toEqual(["old-editing"]);
    expect(s.thisWeek.map((c) => c.id)).toEqual(["wk-answer", "req"]);
  });

  it("lists what was done today and counts posts per platform", () => {
    expect(s.doneToday.map((c) => c.id)).toEqual(["posted"]);
    expect(s.postedToday).toEqual({ linkedin: 1, x: 0 });
  });

  it("filters by platform", () => {
    const x = boardSections(desk({ cards }), today, tz, "x");
    expect(x.today.linkedin).toEqual([]);
    expect(x.today.x.map((c) => c.id)).toEqual(["x1"]);
  });
});
