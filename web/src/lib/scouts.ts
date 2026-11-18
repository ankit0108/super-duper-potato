import type { DeskState } from "@/types";

export type ScoutReport = NonNullable<DeskState["scouts"]>[number];
export type Opportunity = NonNullable<ScoutReport["opportunities"]>[number];
export type ScoutNote = Pick<Opportunity, "score" | "marks" | "evidence_level" | "evidence" | "why" | "opening" | "risk" | "window" | "reply_to" | "visual" | "rank">;

/** What a scout's evidence is: counts a public site reported, a post or coverage a search found, or neither. */
export const EVIDENCE_LABEL: Record<string, { label: string; tone: "ok" | "info" | "neutral"; hint: string }> = {
  observed: { label: "Observed activity", tone: "ok", hint: "A public site reported counts for it (points, upvotes, likes or comments)." },
  indexed: { label: "Found, reach unknown", tone: "info", hint: "It was found on the platform or covered by several outlets; nothing is known about how far it went." },
  hypothesis: { label: "Scout's guess", tone: "neutral", hint: "No sign of traction yet: the scout thinks it could travel." },
};

export const MARK_LABEL: Record<string, string> = {
  timing: "Timing",
  live: "Live now",
  traction: "Traction",
  stakes: "Stakes for readers",
  conversation: "Conversation",
  keep: "Worth saving",
  standing: "Your standing",
  hook: "Reply or quote hook",
  edge: "What you can add",
  quotable: "Quotable",
};

export const WINDOW_LABEL: Record<string, string> = { today: "Post today", this_week: "Good this week", evergreen: "Keeps" };
export const RISK_LABEL: Record<string, string> = { saturated: "Already everywhere", late: "Getting late", "thin evidence": "Thin evidence", sensitive: "Handle with care" };

/** A scout's marks in the order it scores them, each out of 3. */
export function markRows(marks: Record<string, number> | null | undefined): Array<{ key: string; label: string; value: number }> {
  const order = Object.keys(MARK_LABEL);
  const place = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length);
  return Object.entries(marks ?? {})
    .sort(([a], [b]) => place(a) - place(b))
    .map(([key, value]) => ({ key, label: MARK_LABEL[key] ?? key, value: Math.max(0, Math.min(3, Number(value) || 0)) }));
}

/** The reports for one platform, newest first. */
export function reportsFor(reports: ScoutReport[] | null | undefined, platform: string): ScoutReport[] {
  return (reports ?? []).filter((r) => r.platform === platform).sort((a, b) => (a.local_date < b.local_date ? 1 : -1));
}

/** A "Draft this" that the pipeline hasn't picked up yet (overlay.ts marks it). */
export const PENDING_CARD = "pending";

export function searchLine(search: DeskState["scout_search"] | null | undefined): string {
  if (!search?.available) return "Working from feeds only. Add the TAVILY_API_KEY secret (free at tavily.com) and the scouts will also search public LinkedIn and X posts each morning.";
  const used = `${(search.used ?? 0).toLocaleString("en")} of ${(search.cap ?? 0).toLocaleString("en")} searches used this month`;
  return search.error ? `Web search is set up, but the last search failed (${search.error}); ${used}.` : `Web search is on: ${used}.`;
}

export const SHAPE_LABEL: Record<string, string> = {
  news_take: "News, then your take",
  lesson: "A lesson from real work",
  framework: "A framework worth saving",
  disagreement: "A defensible disagreement",
  number: "One number and what it means",
  observation: "One distinctive observation",
  reply: "A reply that adds one thing",
  quote: "A quote-post that stands alone",
  thread: "A thread",
  question: "A question practitioners can answer",
};

type Group = { n?: number; avg?: number | null };
/** Whether the scout's scores match what he posts, in a sentence; null until both groups have a few cards. */
export function calibrationLine(stats: unknown, platform: string): string | null {
  const row = ((stats as { scouts?: Record<string, { posted?: Group; passed?: Group }> } | null | undefined)?.scouts ?? {})[platform];
  const posted = row?.posted;
  const passed = row?.passed;
  if (!posted?.n && !passed?.n) return null;
  const pct = (g?: Group) => `${Math.round((g?.avg ?? 0) * 100)}%`;
  if ((posted?.n ?? 0) < 3 || (passed?.n ?? 0) < 3) return "Too few cards yet to say whether the scout's score matches what you post.";
  return `So far, the cards you posted had an average scout score of ${pct(posted)} (${posted!.n} cards); the ones you skipped or let expire, ${pct(passed)} (${passed!.n} cards).`;
}

export type EditorSlate = NonNullable<DeskState["editor_slates"]>[number];
export type Runner = NonNullable<EditorSlate["runners_up"]>[number];

/** Today's runner-ups per platform, from the newest set of the day (a fresh set replaces the morning's list). */
export function runnerUps(slates: EditorSlate[] | null | undefined, today: string): Array<{ slate: EditorSlate; runner: Runner }> {
  const out: Array<{ slate: EditorSlate; runner: Runner }> = [];
  for (const platform of ["linkedin", "x"] as const) {
    const slate = (slates ?? []).filter((sl) => sl.platform === platform && sl.local_date === today).sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0];
    for (const runner of slate?.runners_up ?? []) out.push({ slate, runner });
  }
  return out;
}

/** Whether he posts from the top of the editor's order, in a sentence; null until there are a few posts. */
export function editorLine(stats: unknown, platform: string): string | null {
  const row = ((stats as { editors?: Record<string, { posted_top_half?: number; posted_bottom_half?: number }> } | null | undefined)?.editors ?? {})[platform];
  const top = row?.posted_top_half ?? 0;
  const bottom = row?.posted_bottom_half ?? 0;
  if (top + bottom < 3) return null;
  return `Of your last ${top + bottom} posts from the editor's sets, ${top} came from the top half of its order.`;
}
