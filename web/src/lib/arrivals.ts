// What a new desk.json finished of the work he was waiting on, for "ready · Open" toasts: a cross-post's new card,
// a visual, a rewrite or draft, and a new set of cards.
import type { DeskState } from "@/types";
import { PLATFORM_LABEL } from "./format";

export type Arrival = { tone: "ok" | "warn"; text: string; cardId: string | null };

const quote = (t: string) => `“${t.length > 60 ? `${t.slice(0, 57).trimEnd()}…` : t}”`;

/** Compare the desk he was looking at with the new one. `now` bounds "new cards" to ones delivered recently. */
export function arrivals(before: DeskState | null, after: DeskState | null, now: Date = new Date()): Arrival[] {
  if (!before?.cards || !after?.cards) return [];
  const next = new Map(after.cards.map((c) => [c.id, c]));
  const known = new Set(before.cards.map((c) => c.id));
  const out: Arrival[] = [];
  const announced = new Set<string>();

  for (const old of before.cards) {
    const w = old.work;
    if (!w) continue;
    const cur = next.get(old.id);
    if (!cur || cur.work) continue; // still on it
    if (w.target_platform && w.target_platform !== old.platform) {
      const made = after.cards.find((c) => c.crosspost_of === old.id && c.platform === w.target_platform && c.status !== "drafting");
      if (!made) continue;
      announced.add(made.id);
      const where = PLATFORM_LABEL[made.platform];
      out.push(
        made.status === "failed"
          ? { tone: "warn", cardId: made.id, text: `The ${where} version of ${quote(old.title)} couldn't be drafted. Open it to try again.` }
          : { tone: "ok", cardId: made.id, text: `Your ${where} version of ${quote(old.title)} is ready.` },
      );
    } else if (w.kind === "visual") {
      const drawn = !!cur.visual?.created_at && cur.visual.created_at !== old.visual?.created_at;
      out.push(
        drawn
          ? { tone: "ok", cardId: cur.id, text: `The visual for ${quote(cur.title)} is ready.` }
          : { tone: "warn", cardId: cur.id, text: `The visual for ${quote(cur.title)} didn't work out. Open the card to see why.` },
      );
    } else if (cur.status === "failed") {
      out.push({ tone: "warn", cardId: cur.id, text: `Drafting ${quote(cur.title)} failed. Open it to try again.` });
    } else if (cur.draft) {
      out.push({ tone: "ok", cardId: cur.id, text: w.kind === "rewrite" ? `The rewrite of ${quote(cur.title)} is ready.` : `The draft of ${quote(cur.title)} is ready.` });
    }
  }

  // A new set (fresh posts he asked for, or the morning's) that landed while the desk was open.
  const recent = now.getTime() - 6 * 3600_000;
  const fresh = after.cards.filter(
    (c) => !known.has(c.id) && !announced.has(c.id) && !c.crosspost_of && !!c.delivery_id && new Date(c.created_at).getTime() >= recent,
  );
  if (fresh.length) out.push({ tone: "ok", cardId: null, text: fresh.length === 1 ? "A new post is ready on the board." : `${fresh.length} new posts are ready on the board.` });
  return out;
}
