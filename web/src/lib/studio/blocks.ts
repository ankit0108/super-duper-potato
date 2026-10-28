// The Studio's replies are plain text with fenced blocks the desk turns into things you can use: a post you can
// edit and post, a list of ideas, a visual it draws (pbs/prompts/studio.md says how the model writes them).

import type { Platform, Visual } from "@/types";

export type StudioPost = {
  platform: Platform;
  format: "li_text" | "x_single" | "x_thread";
  text: string;
  posts: string[];
  hooks: string[];
  hashtags: string[];
  first_comment: string;
  pillar: string | null;
  post_type: string | null;
  sources: Array<{ title: string; url: string }>;
};
export type StudioIdea = { title: string; platform: Platform | null; angle: string; why: string };
export type StudioVisual = Visual & { platform: Platform; use_photo: boolean };

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "post"; post: StudioPost }
  | { kind: "ideas"; ideas: StudioIdea[] }
  | { kind: "visual"; visual: StudioVisual }
  | { kind: "pending"; name: string }
  | { kind: "broken"; name: string; raw: string };

const FENCE = /```(post|ideas|visual|json)?[ \t]*\r?\n([\s\S]*?)(```|$)/g;
const str = (v: unknown, max = 30000) => (typeof v === "string" ? v.slice(0, max) : "");
const strList = (v: unknown, max = 20) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && !!x.trim()).slice(0, max) : []);

function parseJson(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    // Models sometimes leave a trailing comma before } or ].
    try {
      return JSON.parse(raw.replace(/,\s*([}\]])/g, "$1"));
    } catch {
      return undefined;
    }
  }
}

export function toPost(v: unknown): StudioPost | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  const platform: Platform = o.platform === "x" ? "x" : "linkedin";
  let format = str(o.format) as StudioPost["format"];
  const posts = strList(o.posts, 25);
  if (platform === "linkedin") format = "li_text";
  else format = posts.length > 1 || format === "x_thread" ? "x_thread" : "x_single";
  const text = str(o.text);
  if (!text.trim() && !posts.length) return null;
  const sources = Array.isArray(o.sources)
    ? o.sources
        .map((s) => (s && typeof s === "object" ? { title: str((s as Record<string, unknown>).title, 300), url: str((s as Record<string, unknown>).url, 2000) } : null))
        .filter((s): s is { title: string; url: string } => !!s && /^https?:\/\//.test(s.url))
        .slice(0, 8)
    : [];
  return {
    platform,
    format,
    text: format === "x_thread" && !posts.length ? "" : text,
    posts: format === "x_thread" ? (posts.length ? posts : text.split(/\n\s*\n/).filter((p) => p.trim())) : [],
    hooks: strList(o.hooks, 3),
    hashtags: strList(o.hashtags, 10).map((t) => (t.startsWith("#") ? t : `#${t}`).replace(/\s+/g, "")),
    first_comment: str(o.first_comment, 1000),
    pillar: str(o.pillar, 60) || null,
    post_type: str(o.post_type, 40) || null,
    sources,
  };
}

const KINDS = ["carousel", "flow", "compare", "list", "stat", "quote"] as const;

export function toVisual(v: unknown): StudioVisual | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  const kind = (KINDS as readonly string[]).includes(str(o.kind)) ? (str(o.kind) as Visual["kind"]) : "carousel";
  const items = Array.isArray(o.items)
    ? o.items
        .map((it) => (it && typeof it === "object" ? { title: str((it as Record<string, unknown>).title, 200), body: str((it as Record<string, unknown>).body, 1000) } : null))
        .filter((it): it is { title: string; body: string } => !!it && !!(it.title || it.body))
        .slice(0, 12)
    : [];
  if (!str(o.title) && !items.length) return null;
  return {
    kind,
    title: str(o.title, 200),
    subtitle: str(o.subtitle, 300) || null,
    items,
    caption: str(o.caption, 300) || null,
    alt_text: str(o.alt_text, 1500),
    sources: [],
    unsourced: [],
    platform: o.platform === "x" ? "x" : "linkedin",
    use_photo: o.use_photo === true,
  };
}

function toIdeas(v: unknown): StudioIdea[] | null {
  const list = Array.isArray(v) ? v : v && typeof v === "object" && Array.isArray((v as { ideas?: unknown }).ideas) ? (v as { ideas: unknown[] }).ideas : null;
  if (!list) return null;
  const ideas = list
    .map((i) => {
      if (!i || typeof i !== "object") return null;
      const o = i as Record<string, unknown>;
      const title = str(o.title, 300);
      if (!title) return null;
      return { title, platform: o.platform === "x" ? "x" : o.platform === "linkedin" ? "linkedin" : null, angle: str(o.angle, 600), why: str(o.why, 600) } as StudioIdea;
    })
    .filter((i): i is StudioIdea => !!i)
    .slice(0, 8);
  return ideas.length ? ideas : null;
}

/** A reply as text and blocks, in order. While a reply is streaming, a block that hasn't closed yet is "pending". */
export function parseReply(reply: string): Segment[] {
  const out: Segment[] = [];
  let at = 0;
  const pushText = (t: string) => {
    const clean = t.replace(/^\s*\n|\n\s*$/g, "");
    if (clean.trim()) out.push({ kind: "text", text: clean });
  };
  for (const m of reply.matchAll(FENCE)) {
    const name = m[1] ?? "";
    const closed = m[3] === "```";
    pushText(reply.slice(at, m.index));
    at = (m.index ?? 0) + m[0].length;
    if (!closed) {
      out.push({ kind: "pending", name: name || "block" });
      continue;
    }
    const data = parseJson(m[2].trim());
    // An unnamed or ```json block is read by its shape.
    const guess = name === "json" || name === "" ? (Array.isArray(data) ? "ideas" : data && typeof data === "object" && "kind" in data ? "visual" : "post") : name;
    const seg =
      guess === "post"
        ? (() => {
            const p = toPost(data);
            return p ? ({ kind: "post", post: p } as Segment) : null;
          })()
        : guess === "ideas"
          ? (() => {
              const i = toIdeas(data);
              return i ? ({ kind: "ideas", ideas: i } as Segment) : null;
            })()
          : (() => {
              const v = toVisual(data);
              return v ? ({ kind: "visual", visual: v } as Segment) : null;
            })();
    if (seg) out.push(seg);
    else if (name === "json" || name === "") pushText(m[0]);
    else out.push({ kind: "broken", name, raw: m[2] });
  }
  pushText(reply.slice(at));
  return out;
}

/** The post as it goes out: the text (or the thread's posts) without the blocks around it. */
export const postText = (p: StudioPost) => (p.format === "x_thread" ? p.posts.join("\n\n") : p.text);
