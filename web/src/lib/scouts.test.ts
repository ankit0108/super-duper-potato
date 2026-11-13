import { describe, expect, it } from "vitest";
import type { DeskState, InboxEvent } from "@/types";
import { applyEvents } from "./overlay";
import { PENDING_CARD, markRows, reportsFor, searchLine, type ScoutReport } from "./scouts";

const report = (platform: "linkedin" | "x", local_date: string): ScoutReport => ({
  id: `sr_${platform}_${local_date}`,
  platform,
  local_date,
  created_at: `${local_date}T20:00:00Z`,
  status: "ok",
  opportunities: [
    { id: "top_a", title: "A", rank: 1, score: 0.8, card_id: "crd_1" },
    { id: "top_b", title: "B", rank: 2, score: 0.6 },
  ],
});

describe("the scouts' reports", () => {
  it("lists a platform's reports newest first", () => {
    const all = [report("linkedin", "2026-11-08"), report("x", "2026-11-10"), report("linkedin", "2026-11-10")];
    expect(reportsFor(all, "linkedin").map((r) => r.local_date)).toEqual(["2026-11-10", "2026-11-08"]);
    expect(reportsFor(null, "x")).toEqual([]);
  });

  it("names each mark and keeps it between 0 and 3", () => {
    expect(markRows({ other: 2, keep: -1, traction: 7, timing: 3 })).toEqual([
      { key: "timing", label: "Timing", value: 3 },
      { key: "traction", label: "Traction", value: 3 },
      { key: "keep", label: "Worth saving", value: 0 },
      { key: "other", label: "other", value: 2 },
    ]);
    expect(markRows(null)).toEqual([]);
  });

  it("says whether the scouts can search", () => {
    expect(searchLine(null)).toMatch(/feeds only.*TAVILY_API_KEY/);
    expect(searchLine({ available: true, used: 41, cap: 900 })).toBe("Web search is on: 41 of 900 searches used this month.");
    expect(searchLine({ available: true, used: 3, cap: 900, error: "HTTP 401" })).toMatch(/last search failed \(HTTP 401\)/);
  });

  it("shows Draft this as drafting until the pipeline links the card", () => {
    const desk = { cards: [], scouts: [report("linkedin", "2026-11-10")] } as unknown as DeskState;
    const ev = { id: "e1", at: "2026-11-10T21:00:00Z", type: "scout.draft", report_id: "sr_linkedin_2026-11-10", topic_id: "top_b" } as InboxEvent;
    const { desk: view } = applyEvents(desk, [ev]);
    const opps = view.scouts![0].opportunities!;
    expect(opps.map((o) => o.card_id ?? null)).toEqual(["crd_1", PENDING_CARD]);
  });
});
