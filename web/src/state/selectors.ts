import type { Card, DeskState, Platform } from "@/types";
import { localDateKey } from "@/lib/time";

export type BoardSections = {
  needsYou: Card[];
  today: Record<Platform, Card[]>;
  inProgress: Card[];
  thisWeek: Card[];
  doneToday: Card[];
  counts: Record<"all" | Platform, number>;
  postedToday: Record<Platform, number>;
};

const byRank = (a: Card, b: Card) => (a.rank ?? 99) - (b.rank ?? 99) || (b.score ?? 0) - (a.score ?? 0);
const byNewest = (a: Card, b: Card) => (b.created_at ?? "").localeCompare(a.created_at ?? "");

/** A set within today's picks: the morning's (1), a fresh set he asked for (2, 3, …), or cross-posts he made of
 * earlier cards (Infinity: newest of all). */
export function setNumber(c: Card, today: string): number {
  const id = c.delivery_id ?? "";
  if (!id.startsWith(`dly_${today}`)) return Number.POSITIVE_INFINITY;
  const m = /^_(\d+)$/.exec(id.slice(`dly_${today}`.length));
  return m ? Number(m[1]) : 1;
}

export type TodaySet = { key: string; kind: "morning" | "fresh" | "crossposts"; at: string | null; cards: Card[] };

/** Today's cards for one platform, split into sets, newest set first (they arrive sorted that way). */
export function todaySets(cards: Card[], today: string): TodaySet[] {
  const out: TodaySet[] = [];
  for (const c of cards) {
    const n = setNumber(c, today);
    const key = String(n);
    let set = out.find((s) => s.key === key);
    if (!set) {
      set = { key, kind: n === Number.POSITIVE_INFINITY ? "crossposts" : n === 1 ? "morning" : "fresh", at: c.delivered_at ?? c.created_at ?? null, cards: [] };
      out.push(set);
    }
    set.cards.push(c);
  }
  return out;
}

export function boardSections(view: DeskState | null, today: string, tz: string, platform: "all" | Platform): BoardSections {
  const all = view?.cards ?? [];
  const matches = (c: Card) => platform === "all" || c.platform === platform;
  const changedToday = (c: Card) => localDateKey(c.status_changed_at ?? c.updated_at ?? c.created_at, tz) === today;
  // Today's sets, plus the cross-posts he made today of earlier cards (they belong with what he's working on).
  const deliveredToday = (c: Card) =>
    (!!c.delivery_id && c.delivery_id.startsWith(`dly_${today}`)) || (!!c.crosspost_of && localDateKey(c.created_at, tz) === today);

  const needsYou: Card[] = [];
  const today_: Record<Platform, Card[]> = { linkedin: [], x: [] };
  const inProgress: Card[] = [];
  const thisWeek: Card[] = [];
  const doneToday: Card[] = [];
  const postedToday: Record<Platform, number> = { linkedin: 0, x: 0 };
  const counts = { all: 0, linkedin: 0, x: 0 };

  for (const c of all) {
    if (c.status === "posted" && changedToday(c)) postedToday[c.platform] += 1;
    const active = ["suggested", "needs_input", "blocked", "failed", "editing", "drafting"].includes(c.status);
    if (active) {
      counts.all += 1;
      counts[c.platform] += 1;
    }
    if (!matches(c)) continue;
    if (c.status === "posted" || c.status === "skipped") {
      if (changedToday(c)) doneToday.push(c);
      continue;
    }
    if (!active) continue;
    // Today's set stays together in rank order, whatever state each card is in.
    if (deliveredToday(c)) today_[c.platform].push(c);
    else if (c.status === "blocked" || c.status === "failed") needsYou.push(c);
    else if (c.status === "editing") inProgress.push(c);
    else thisWeek.push(c);
  }
  needsYou.sort(byNewest);
  // Newest set first (a fresh set above the morning's), each in rank order; his cross-posts of earlier cards on top.
  const newestSetFirst = (a: Card, b: Card) => setNumber(b, today) - setNumber(a, today) || byRank(a, b) || byNewest(a, b);
  today_.linkedin.sort(newestSetFirst);
  today_.x.sort(newestSetFirst);
  inProgress.sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));
  thisWeek.sort((a, b) => Number(b.status === "needs_input") - Number(a.status === "needs_input") || byNewest(a, b));
  doneToday.sort((a, b) => (b.status_changed_at ?? "").localeCompare(a.status_changed_at ?? ""));
  return { needsYou, today: today_, inProgress, thisWeek, doneToday, counts, postedToday };
}

export function evidenceFor(card: Card): string {
  const parts = [card.title];
  for (const s of card.sources ?? []) parts.push(s.title ?? "", s.summary ?? "", s.orig_title ?? "");
  for (const a of card.answers ?? []) parts.push(a.answer);
  return parts.filter(Boolean).join("\n");
}
