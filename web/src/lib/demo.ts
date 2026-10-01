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

/** Like the pipeline: his answers carry the personal part (nothing added), the first source the context. */
function draftFromAnswers(card: Card): Card["draft"] {
  const answers = (card.answers ?? []).map((a) => a.answer.trim()).filter(Boolean);
  const source = card.sources?.[0];
  const context = source ? `Context: ${source.title}${source.publisher ? ` (${source.publisher})` : ""}.` : "";
  if (card.format === "x_thread") return { text: "", posts: [...answers.slice(0, 4), ...(context ? [context] : [])] };
  if (card.platform === "x") return { text: (answers[0] ?? "").slice(0, 270), posts: [] };
  return { text: [...answers, context].filter(Boolean).join("\n\n"), posts: [] };
}

/** Like the pipeline: without answers, analysis from the sources only. */
function draftFromSources(card: Card): Card["draft"] {
  const facts = (card.sources ?? []).slice(0, 2).map((s) => s.title).filter(Boolean);
  const text = [`${card.angle ?? card.title}.`, ...facts, card.why_now ?? ""].filter(Boolean).join("\n\n");
  return { text: card.platform === "x" ? text.slice(0, 270) : text, posts: card.format === "x_thread" ? [text.slice(0, 270)] : [] };
}

const PILLAR_FOR: Record<string, string> = {
  research: "tech", industry: "tech", receipts: "tech", learning: "tech", tech: "industry", startups: "industry", affairs: "industry", life: "learning",
};
const DEMO_TAGS: Record<string, string[]> = { linkedin: ["#AI", "#Automation", "#FutureOfWork"], x: ["#AI"] };

/** Sentences packed into posts of at most `max` characters. */
function packPosts(sentences: string[], max: number, limit: number): string[] {
  const posts: string[] = [];
  for (const s of sentences) {
    const last = posts[posts.length - 1];
    if (last && `${last} ${s}`.length <= max) posts[posts.length - 1] = `${last} ${s}`;
    else posts.push(s.slice(0, max));
  }
  return posts.slice(0, limit);
}

/**
 * "Get fresh posts" in the demo: there's no pipeline to scout, so earlier days' unused picks come back as a new
 * set for today (the real run finds new stories, ranks them against today's and drafts them).
 */
function demoFreshSet(desk: DeskState, cards: Card[], ev: Extract<InboxEvent, { type: "run.request" }>, now: string): Card[] {
  const today = desk.delivery?.local_date ?? now.slice(0, 10);
  const base = `dly_${today}`;
  let n = 2;
  while (cards.some((c) => c.delivery_id === `${base}_${n}`)) n++;
  const settings = desk.settings as Record<string, any> | undefined;
  const platforms: Card["platform"][] = ev.platforms?.length ? ev.platforms : ["linkedin", "x"];
  const out: Card[] = [];
  for (const p of platforms) {
    const want = ev.per_platform ?? Math.min(3, settings?.platforms?.[p]?.slots ?? 3);
    const pool = cards.filter((c) => c.platform === p && c.kind === "news" && !!c.draft && !c.crosspost_of && !(c.delivery_id ?? "").startsWith(base) && c.status !== "posted");
    pool.slice(0, want).forEach((c, i) =>
      out.push({
        ...c,
        id: `demo_fresh_${n}_${p}_${i + 1}`,
        delivery_id: `${base}_${n}`,
        rank: i + 1,
        status: "suggested",
        created_at: now,
        delivered_at: now,
        updated_at: now,
        status_changed_at: now,
        work: null,
        working: null,
        skip: null,
        post_id: null,
        visual: null,
      }),
    );
  }
  return out;
}

/** Like the pipeline's adapt(): a version for the other platform, delivered with the original's set. */
function crosspostCard(desk: DeskState, source: Card, ev: Extract<InboxEvent, { type: "card.crosspost" }>, now: string): Card {
  const platform = ev.target_platform;
  const strategy = (desk.settings?.strategy ?? {}) as Record<string, Record<string, { formats?: string[] }>>;
  const pillars = strategy[platform] ?? {};
  const pillar = pillars[source.pillar] ? source.pillar : pillars[PILLAR_FOR[source.pillar] ?? ""] ? PILLAR_FOR[source.pillar] : (Object.keys(pillars)[0] ?? source.pillar);
  const formats = pillars[pillar]?.formats ?? [platform === "linkedin" ? "li_text" : "x_single"];
  const wanted = ev.target_format ?? (platform === "linkedin" ? "li_text" : "x_single");
  const format = (formats.includes(wanted) ? wanted : formats[0]) as Card["format"];
  const base = source.working ?? source.draft ?? { text: "", posts: [] };
  const full = base.posts?.length ? base.posts.join(" ") : (base.text ?? "");
  const sentences = splitSentences(full.replace(/\s*\n+\s*/g, " ")).filter(Boolean);
  let draft: Card["draft"];
  if (format === "x_thread") draft = { text: "", posts: packPosts(sentences, 270, 5) };
  else if (platform === "x") draft = { text: packPosts(sentences, 270, 1)[0] ?? "", posts: [] };
  else draft = { text: (base.posts?.length ? base.posts : sentences).join("\n\n"), posts: [] };
  draft = { ...draft, first_comment: source.draft?.first_comment ?? null };
  return {
    id: `demo_xp_${source.id}_${platform}_${ev.id.slice(-6)}`,
    kind: "adapt",
    crosspost_of: source.id,
    delivery_id: source.delivery_id ?? null,
    arm: `${platform}:${pillar}:${format}`,
    platform,
    pillar,
    format,
    mode: source.mode,
    title: source.title,
    why_now: source.why_now,
    angle: source.angle,
    sources: source.sources ?? [],
    hooks: source.hooks ?? [],
    hashtags: DEMO_TAGS[platform],
    draft,
    draft_original: draft,
    draft_state: "full",
    draft_basis: source.draft_basis ?? null,
    status: "suggested",
    created_at: now,
    updated_at: now,
    delivered_at: now,
    revision: 1,
  };
}

/** Like the pipeline's visuals.make_visual (with the demo model): a visual from the post's own sentences. */
type DemoImage = NonNullable<NonNullable<Card["visual"]>["image"]>;

/** A picture the demo already has (made by the pipeline's demo image service), to stand in for a new one. */
export function demoImage(desk: DeskState): DemoImage | null {
  for (const c of desk.cards ?? []) if (c.visual?.image) return c.visual.image;
  return null;
}

export function demoVisual(card: Card, kind: string, now: string, image: DemoImage | null = null, background = false): NonNullable<Card["visual"]> {
  const clipTitle = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);
  if (kind === "image") {
    return {
      kind: "image",
      title: clipTitle(card.title, 60),
      subtitle: null,
      items: [],
      caption: null,
      alt_text: `AI-generated illustration: a calm scene for a post about ${card.title}`.slice(0, 600),
      sources: [],
      unsourced: [],
      image: image ? { ...image, created_at: now } : null,
      created_at: now,
    };
  }
  const drawn = demoVisualDrawn(card, kind, now);
  return background && image && ["carousel", "stat", "quote"].includes(drawn.kind) ? { ...drawn, image: { ...image, created_at: now } } : drawn;
}

function demoVisualDrawn(card: Card, kind: string, now: string): NonNullable<Card["visual"]> {
  const d = card.working ?? card.draft ?? { text: "", posts: [] };
  const text = d.posts?.length ? d.posts.join(" ") : (d.text ?? "");
  const sentences = splitSentences(text.replace(/\s*\n+\s*/g, " ")).filter((s) => s.split(/\s+/).length >= 4);
  const label = (s: string, n: number) => {
    const head = s.split(/[:,;–—]/)[0].replace(/[.?!]+$/, "");
    const words = head.split(/\s+/);
    return words.length <= n ? head : `${words.slice(0, n).join(" ")}…`;
  };
  const figure = /\d[\d,.]*\s?%|\$\s?\d[\d,.]*\s?(?:[mb]n?|billion|million)?|\d[\d,.]*/i.exec(text)?.[0];
  // A big number needs a figure: a number word will do ("three corridors"); without one it's a list.
  const word = /\b(two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|hundred)\b/i.exec(text)?.[1];
  const wanted = kind !== "auto" ? kind : card.platform === "linkedin" ? "carousel" : figure ? "stat" : "list";
  const chosen = wanted === "stat" && !figure && !word ? "list" : wanted;
  const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);
  const source = card.sources?.[0];
  let items: Array<{ title: string; body: string }>;
  if (chosen === "stat") {
    const fig = figure ?? `${word![0].toUpperCase()}${word!.slice(1).toLowerCase()}`;
    const about = sentences.find((s) => s.includes(fig) || s.toLowerCase().includes(fig.toLowerCase())) ?? sentences[0] ?? card.title;
    items = [{ title: fig, body: clip(about, 120) }];
  }
  else if (chosen === "quote") items = [{ title: source?.publisher ?? "The source", body: clip(sentences[0] ?? card.title, 200) }];
  else if (chosen === "compare") {
    const half = Math.max(1, Math.floor(sentences.length / 2));
    items = [
      { title: "What it says", body: sentences.slice(0, half).slice(0, 4).map((s) => clip(s, 60)).join("\n") },
      { title: "What it means", body: sentences.slice(half).slice(0, 4).map((s) => clip(s, 60)).join("\n") || "Watch what happens next" },
    ];
  } else {
    const n = chosen === "carousel" ? (card.platform === "x" ? 3 : 6) : 5;
    const chunks = (sentences.length ? sentences : [card.title]).slice(0, n);
    while (chunks.length < 3) chunks.push(`Step ${chunks.length + 1}`);
    items = chunks.map((s) => ({ title: label(s, chosen === "flow" ? 4 : 6), body: clip(s, chosen === "carousel" ? 220 : 100) }));
  }
  return {
    kind: chosen as NonNullable<Card["visual"]>["kind"],
    title: clip(card.title, 90),
    subtitle: card.angle ? clip(card.angle, 140) : null,
    items,
    caption: source ? `Source: ${source.title}${source.publisher ? ` (${source.publisher})` : ""}` : null,
    alt_text: `${chosen}: ${card.title}. ${items.map((it) => [it.title, it.body].filter(Boolean).join(" ")).join("; ")}`.slice(0, 600),
    sources: source ? [0] : [],
    unsourced: [],
    created_at: now,
  };
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
      cards[idx] = { ...c, draft: draftFromAnswers(c), draft_state: "full", draft_basis: "answers", status: "suggested", work: null, working: null, revision: (c.revision ?? 0) + 1, updated_at: now };
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
    if (ev.type === "card.crosspost" && idx >= 0 && cards[idx].work?.target_platform === ev.target_platform) {
      cards.unshift(crosspostCard(next, cards[idx], ev, now));
      cards[idx + 1] = { ...cards[idx + 1], work: null };
    }
    if (ev.type === "card.visual" && idx >= 0) {
      const c = cards[idx];
      cards[idx] = { ...c, visual: demoVisual(c, ev.kind ?? "auto", now, demoImage(next), !!ev.ai_background), work: null, working: c.working ? { ...c.working, visual: null } : c.working, updated_at: now };
    }
    if (ev.type === "card.draft_now" && idx >= 0) {
      const c = cards[idx];
      cards[idx] = { ...c, draft: draftFromSources(c), draft_state: "full", draft_basis: "sources", status: "suggested", work: null, revision: (c.revision ?? 0) + 1, updated_at: now };
    }
    if (ev.type === "run.request" && ev.force && ev.tasks?.includes("morning")) {
      cards.unshift(...demoFreshSet(next, cards, ev, now));
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
      const search = {
        interpretation: `${ev.query}, as it relates to your pillars`,
        queries: [ev.query, `${ev.query} enterprise`],
        exclude: [],
        recency_days: 14,
        results: 24,
        kept: 8,
        checked: true,
      };
      next = { ...next, requests: (next.requests ?? []).map((r) => (r.id === ev.request_id ? { ...r, status: "done", card_ids: ids, completed_at: now, search } : r)) };
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
