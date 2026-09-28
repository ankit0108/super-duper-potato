// Hashtags are chosen on the card and added at the end when he copies, opens the app or marks it posted.
// Mirrors pbs/hashtags.py: the pipeline strips them again to compare what he posted with the draft.
import type { FormatName } from "@/types";

const WORDS = /[\p{L}\p{N}]+/gu;

/** "#AI agents", "ai agents" or "AIAgents" -> "#AIAgents"; null for numbers, blanks and very long tags. */
export function normalizeTag(raw: string): string | null {
  const words = raw.trim().replace(/^#+/, "").match(WORDS) ?? [];
  if (!words.length) return null;
  const tag = words.length === 1 ? words[0] : words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join("");
  if (/^\d+$/.test(tag) || tag.length > 30) return null;
  return `#${tag}`;
}

export function sameTag(a: string, b: string): boolean {
  return a.replace(/^#/, "").toLowerCase() === b.replace(/^#/, "").toLowerCase();
}

/** Adds the chosen tags: a last line on LinkedIn, the end of the post on X (post 1 of a thread). */
export function withHashtags(format: FormatName, body: { text: string; posts: string[] }, tags: string[]): { text: string; posts: string[] } {
  if (!tags.length) return body;
  const line = tags.join(" ");
  if (format === "x_thread") {
    const posts = [...body.posts];
    if (posts.length) posts[0] = `${posts[0].trimEnd()} ${line}`;
    return { text: body.text, posts };
  }
  if (format === "li_text") return { text: body.text.trim() ? `${body.text.trimEnd()}\n\n${line}` : line, posts: body.posts };
  return { text: body.text.trim() ? `${body.text.trimEnd()} ${line}` : line, posts: body.posts };
}

/** The post without the tags added at its end (to compare what went out with the draft). */
export function withoutHashtags(text: string, tags: string[]): string {
  let out = text.trimEnd();
  const line = tags.join(" ");
  if (line && out.endsWith(line)) out = out.slice(0, out.length - line.length).trimEnd();
  return out;
}
