// Demo mode: the desk runs on bundled sample data and simulates what the pipeline would do with each event,
// so every screen can be explored (and tested end to end) without GitHub or a model.
import type { Card, DeskState, InboxEvent } from "@/types";
import { applyEvents } from "./overlay";
import { splitSentences } from "./text";

export async function loadDemoDesk(now = new Date()): Promise<DeskState> {
  const res = await fetch("./demo/desk.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`Demo data missing (${res.status})`);
  return rebaseDemo((await res.json()) as DeskState, now);
}

const DAY_MS = 86_400_000;
const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_WEEK = /^(wkb_)?(\d{4})-W(\d{2})$/;
const DELIVERY_ID = /^dly_(\d{4}-\d{2}-\d{2})(_\d+)?$/;

function localDay(instant: Date, tz: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(instant);
}

function addDays(date: string, days: number): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

/** ISO week label ("2026-W39") of a UTC calendar date. */
export function isoWeek(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  const weekday = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - weekday + 3); // Thursday of this week decides the year
  const year = d.getUTCFullYear();
  const firstThursday = new Date(Date.UTC(year, 0, 4));
  firstThursday.setUTCDate(firstThursday.getUTCDate() - ((firstThursday.getUTCDay() + 6) % 7) + 3);
  const week = 1 + Math.round((d.getTime() - firstThursday.getTime()) / (7 * DAY_MS));
  return `${year}-W${String(week).padStart(2, "0")}`;
}

function shiftWeek(year: string, week: string, days: number): string {
  const jan4 = new Date(Date.UTC(Number(year), 0, 4));
  const monday = new Date(jan4.getTime() - ((jan4.getUTCDay() + 6) % 7) * DAY_MS + (Number(week) - 1) * 7 * DAY_MS);
  return isoWeek(addDays(monday.toISOString().slice(0, 10), Math.round(days / 7) * 7));
}

/** Days to add so the demo's "this morning" is today in the desk's timezone. */
export function demoShiftDays(desk: DeskState, now: Date): number {
  const generated = desk.meta?.generated_at;
  if (!generated) return 0;
  const tz = desk.meta?.timezone ?? "Australia/Melbourne";
  return Math.round((Date.parse(localDay(now, tz)) - Date.parse(localDay(new Date(generated), tz))) / DAY_MS);
}

/**
 * Move the demo to today: every timestamp, date, delivery id and ISO week shifts by the same whole number of
 * days, so relative times ("delivered 40 minutes ago", "3 days ago") and the week's shape stay as recorded.
 */
export function rebaseDemo(desk: DeskState, now = new Date()): DeskState {
  const days = demoShiftDays(desk, now);
  if (!days) return desk;
  const shift = (value: unknown): unknown => {
    if (typeof value === "string") {
      if (ISO_DATETIME.test(value)) {
        const t = Date.parse(value);
        return Number.isNaN(t) ? value : new Date(t + days * DAY_MS).toISOString().replace(".000Z", "Z");
      }
      if (ISO_DATE.test(value)) return addDays(value, days);
      const dly = DELIVERY_ID.exec(value);
      if (dly) return `dly_${addDays(dly[1], days)}${dly[2] ?? ""}`;
      const wk = ISO_WEEK.exec(value);
      if (wk) return `${wk[1] ?? ""}${shiftWeek(wk[2], wk[3], days)}`;
      return value;
    }
    if (Array.isArray(value)) return value.map(shift);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shift(v)]));
    return value;
  };
  return shift(desk) as DeskState;
}

function draftFromAnswers(card: Card): Card["draft"] {
  const answers = (card.answers ?? []).map((a) => a.answer.trim()).filter(Boolean);
  const hook = card.hooks?.[0]?.text ?? card.title;
  const body = answers.join("\n\n");
  if (card.format === "x_thread") return { text: "", posts: [hook, ...answers].slice(0, 5) };
  if (card.platform === "x") return { text: `${answers[0] ?? hook}`.slice(0, 270), posts: [] };
  return { text: `${hook}\n\n${body}\n\nThat's the part the demos skip.`, posts: [] };
}

function rewriteText(card: Card, chips: string[], note: string): Card["draft"] {
  const current = card.working ?? card.draft ?? { text: "", posts: [] };
  const wantShort = chips.includes("Shorter") || /short/i.test(note);
  const sharper = chips.includes("Sharper hook") || /hook/i.test(note);
  if (card.format === "x_thread") {
    const posts = [...(current.posts ?? [])];
    if (sharper && card.hooks?.[1]) posts[0] = card.hooks[1].text;
    return { text: "", posts: wantShort ? posts.slice(0, Math.max(3, posts.length - 1)) : posts };
  }
  let text = current.text ?? "";
  if (sharper && card.hooks?.[1]) {
    const [first, ...rest] = text.split("\n");
    text = [card.hooks[1].text, ...rest].join("\n") || first;
  }
  if (wantShort) {
    const sentences = splitSentences(text);
    text = sentences.slice(0, Math.max(2, Math.ceil(sentences.length * 0.65))).join(" ");
  }
  return { ...current, text, posts: [] };
}

/** Apply events permanently to the demo state, including simulated pipeline work. */
export function processDemoEvents(desk: DeskState, events: InboxEvent[]): DeskState {
  let next = applyEvents(desk, events).desk;
  const cards = [...(next.cards ?? [])];
  const now = new Date().toISOString();
  for (const ev of events) {
    const idx = "card_id" in ev ? cards.findIndex((c) => c.id === (ev as { card_id: string }).card_id) : -1;
    if (ev.type === "card.answers" && idx >= 0) {
      const c = cards[idx];
      cards[idx] = { ...c, draft: draftFromAnswers(c), draft_state: "full", status: "suggested", work: null, updated_at: now };
    }
    if (ev.type === "card.rewrite" && idx >= 0) {
      const c = cards[idx];
      cards[idx] = {
        ...c,
        draft: rewriteText(c, ev.chips ?? [], ev.note ?? ""),
        working: null,
        work: null,
        rewrite_count: (c.rewrite_count ?? 0) + 1,
        revision: (c.revision ?? 0) + 1,
        updated_at: now,
      };
    }
    if (ev.type === "card.draft_now" && idx >= 0) {
      const c = cards[idx];
      const text = `${c.angle ?? c.title}.\n\n${c.why_now ?? ""}`.trim();
      cards[idx] = { ...c, draft: { text, posts: c.format === "x_thread" ? [text] : [] }, draft_state: "full", work: null, updated_at: now };
    }
    if (ev.type === "request.create") {
      const ids: string[] = [];
      for (const [platform, n] of Object.entries(ev.platforms)) {
        for (let i = 1; i <= (n ?? 0); i++) {
          const id = `demo_req_${ev.request_id}_${platform}_${i}`;
          ids.push(id);
          cards.unshift({
            id,
            kind: "request",
            request_id: ev.request_id,
            platform: platform as Card["platform"],
            pillar: platform === "linkedin" ? "industry" : "tech",
            format: platform === "linkedin" ? "li_text" : i % 2 ? "x_single" : "x_thread",
            mode: "external",
            title: ev.query,
            why_now: "You asked for this.",
            angle: `Angle ${i} on ${ev.query}`,
            status: "suggested",
            draft:
              platform === "x" && i % 2 === 0
                ? { text: "", posts: [`${ev.query}: what changed.`, "The part most coverage misses.", "What to watch next."] }
                : { text: `${ev.query}: the practical takeaway for teams doing the work.`, posts: [] },
            hooks: [
              { type: "question", text: `What does ${ev.query} change?` },
              { type: "observation", text: `${ev.query}, minus the hype.` },
              { type: "how-to", text: `How to think about ${ev.query}:` },
            ],
            sources: [],
            created_at: now,
            delivered_at: now,
            rank: i,
          });
        }
      }
      next = { ...next, requests: (next.requests ?? []).map((r) => (r.id === ev.request_id ? { ...r, status: "done", card_ids: ids, completed_at: now } : r)) };
    }
    if (ev.type === "metrics.upload") {
      next = {
        ...next,
        uploads: (next.uploads ?? []).map((u) =>
          u.id === ev.upload_id ? { ...u, status: "processed", processed_at: now, results: { files: ev.paths.map((p) => ({ path: p, metrics: 0, needs_review: 0 })) } } : u,
        ),
      };
    }
  }
  return {
    ...next,
    cards,
    processed_event_ids: [...(next.processed_event_ids ?? []), ...events.map((e) => e.id)],
  };
}
