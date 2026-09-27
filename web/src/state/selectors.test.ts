import { card, desk } from "@/test/fixtures";
import { boardSections } from "./selectors";

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

  it("keeps today's set together in rank order, whatever each card's state, second set after the first", () => {
    expect(s.today.linkedin.map((c) => c.id)).toEqual(["t2", "t1", "t3", "t4"]);
    expect(s.today.x.map((c) => c.id)).toEqual(["x1"]);
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
