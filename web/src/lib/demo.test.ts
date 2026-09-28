import { card, desk, event } from "@/test/fixtures";
import { demoShiftDays, isoWeek, processDemoEvents, rebaseDemo } from "./demo";

describe("isoWeek", () => {
  it.each([
    ["2026-09-28", "2026-W40"],
    ["2026-09-27", "2026-W39"],
    ["2027-01-01", "2026-W53"],
    ["2021-01-03", "2020-W53"],
    ["2024-12-30", "2025-W01"],
  ])("%s is %s", (date, week) => {
    expect(isoWeek(date)).toBe(week);
  });
});

describe("rebaseDemo", () => {
  const base = desk({
    meta: { schema_version: 1, generated_at: "2026-09-27T20:31:00Z", timezone: "Australia/Melbourne", next_delivery_local: "2026-09-29T04:00+10:00" },
    delivery: { id: "dly_2026-09-28", local_date: "2026-09-28", delivered_at: "2026-09-27T19:43:00Z", kind: "morning" },
    cards: [{ id: "crd_1", delivery_id: "dly_2026-09-28_2", platform: "x", pillar: "tech", format: "x_single", title: "Keeps 2026-09-28 in prose", status: "suggested", created_at: "2026-09-27T19:43:00Z" }],
    stats: { weekly: [{ week: "2026-W40" }] },
  } as never);

  it("is a no-op on the demo's own day", () => {
    // 06:40 on 28 Sep in Melbourne: the demo's morning.
    expect(rebaseDemo(base, new Date("2026-09-27T20:40:00Z"))).toBe(base);
  });

  it("moves every date, delivery id and week by whole days", () => {
    const now = new Date("2026-10-06T01:00:00Z"); // 12:00 on Tue 6 Oct in Melbourne: 8 days later
    expect(demoShiftDays(base, now)).toBe(8);
    const out = rebaseDemo(base, now);
    expect(out.meta?.generated_at).toBe("2026-10-05T20:31:00Z");
    expect(out.delivery?.id).toBe("dly_2026-10-06");
    expect(out.delivery?.local_date).toBe("2026-10-06");
    expect(out.cards?.[0].delivery_id).toBe("dly_2026-10-06_2");
    expect(out.cards?.[0].title).toBe("Keeps 2026-09-28 in prose");
    expect((out.stats as { weekly: Array<{ week: string }> }).weekly[0].week).toBe("2026-W41");
    expect(Date.parse(out.meta!.next_delivery_local!)).toBe(Date.parse("2026-10-07T04:00+10:00"));
  });
});

describe("processDemoEvents: cross-posts", () => {
  const settings = { strategy: { linkedin: { industry: { formats: ["li_text"] } }, x: { tech: { formats: ["x_single", "x_thread"] } } } };
  const source = card({ pillar: "industry", delivery_id: "dly_2026-09-28", hashtags: ["#AI", "#RPA", "#Workflows"], draft: { text: "First point here. Second point there.\n\nThird point.", posts: [], first_comment: "Source: https://example.com/a" } });

  it("makes the other platform's version, linked to the original, like the pipeline's adapt()", () => {
    const out = processDemoEvents(desk({ settings, cards: [source] } as never), [event("card.crosspost", { card_id: source.id, target_platform: "x", target_format: "x_thread", mode: "both" })]);
    const made = out.cards!.find((c) => c.crosspost_of === source.id)!;
    expect(made).toMatchObject({ kind: "adapt", platform: "x", pillar: "tech", format: "x_thread", status: "suggested", delivery_id: "dly_2026-09-28" });
    expect(made.draft?.posts?.length).toBeGreaterThan(0);
    expect(made.draft?.posts?.every((p) => p.length <= 270)).toBe(true);
    expect(made.draft?.first_comment).toBe("Source: https://example.com/a");
    const original = out.cards!.find((c) => c.id === source.id)!;
    expect(original.status).toBe("suggested");
    expect(original.work).toBeNull();
  });

  it("switching skips the original as the wrong platform", () => {
    const out = processDemoEvents(desk({ settings, cards: [source] } as never), [event("card.crosspost", { card_id: source.id, target_platform: "x", mode: "switch" })]);
    expect(out.cards!.find((c) => c.id === source.id)!.skip?.reason).toBe("wrong_platform");
    expect(out.cards!.find((c) => c.crosspost_of === source.id)!.format).toBe("x_single");
  });
});
