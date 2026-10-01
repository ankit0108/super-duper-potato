import { card, desk } from "@/test/fixtures";
import { arrivals } from "./arrivals";
import { deployedBuild } from "./version";

const now = new Date("2026-09-28T21:00:00Z");

describe("arrivals", () => {
  it("announces a cross-post's new card, pointing at the new card", () => {
    const li = card({ id: "li1", title: "Agents in production", work: { kind: "rewrite", target_platform: "x", crosspost: "both", requested_at: "2026-09-28T20:50:00Z" } });
    const before = desk({ cards: [li] });
    const after = desk({ cards: [{ ...li, work: null }, card({ id: "x1", platform: "x", crosspost_of: "li1", status: "suggested", created_at: "2026-09-28T20:58:00Z" })] });
    expect(arrivals(before, after, now)).toEqual([{ tone: "ok", cardId: "x1", text: "Your X version of “Agents in production” is ready." }]);
    const failed = desk({ cards: [{ ...li, work: null }, card({ id: "x1", platform: "x", crosspost_of: "li1", status: "failed" })] });
    expect(arrivals(before, failed, now)[0]).toMatchObject({ tone: "warn", cardId: "x1" });
  });

  it("announces a visual, a rewrite and a draft once the work is done, and nothing while it's still going", () => {
    const v = card({ id: "v", title: "Visual card", work: { kind: "visual", visual_kind: "auto", requested_at: "2026-09-28T20:50:00Z" } });
    const r = card({ id: "r", title: "Rewrite card", work: { kind: "rewrite", requested_at: "2026-09-28T20:50:00Z" } });
    const d = card({ id: "d", title: "Draft card", work: { kind: "draft", requested_at: "2026-09-28T20:50:00Z" } });
    const before = desk({ cards: [v, r, d] });
    const done = desk({
      cards: [
        { ...v, work: null, visual: { kind: "list", title: "T", items: [], alt_text: "", created_at: "2026-09-28T20:59:00Z" } },
        { ...r, work: null },
        { ...d, work: null },
      ],
    });
    expect(arrivals(before, done, now).map((a) => [a.cardId, a.tone, a.text])).toEqual([
      ["v", "ok", "The visual for “Visual card” is ready."],
      ["r", "ok", "The rewrite of “Rewrite card” is ready."],
      ["d", "ok", "The draft of “Draft card” is ready."],
    ]);
    expect(arrivals(before, before, now)).toEqual([]);
    const blocked = desk({ cards: [{ ...v, work: null }] }); // the visual was dropped (blocklist, or failed 3 times)
    expect(arrivals(desk({ cards: [v] }), blocked, now)[0]).toMatchObject({ tone: "warn", cardId: "v" });
  });

  it("counts a new set that landed while the desk was open", () => {
    const old = card({ id: "o", delivery_id: "dly_2026-09-29" });
    const fresh = [1, 2, 3].map((i) => card({ id: `f${i}`, delivery_id: "dly_2026-09-29_2", created_at: "2026-09-28T20:59:00Z" }));
    expect(arrivals(desk({ cards: [old] }), desk({ cards: [old, ...fresh] }), now)).toEqual([{ tone: "ok", cardId: null, text: "3 new posts are ready on the board." }]);
    expect(arrivals(null, desk({ cards: fresh }), now)).toEqual([]); // first load: nothing to compare with
  });
});

describe("deployedBuild", () => {
  it("reads version.json without a cache, and gives null when it can't", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const ok = (async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ id: "abc1234-x", at: "2026-10-01T00:00:00Z" }));
    }) as typeof fetch;
    expect(await deployedBuild(ok)).toEqual({ id: "abc1234-x", at: "2026-10-01T00:00:00Z" });
    expect(calls[0][0]).toMatch(/^\.\/version\.json\?t=\d+$/);
    expect(calls[0][1]).toMatchObject({ cache: "no-store" });
    expect(await deployedBuild((async () => new Response("nope", { status: 404 })) as typeof fetch)).toBeNull();
    expect(await deployedBuild((async () => { throw new TypeError("offline"); }) as typeof fetch)).toBeNull();
  });
});
