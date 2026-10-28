// What the Studio sends: its instructions (the Studio kit from desk.json, written by the pipeline from your
// style, the platform guide and your posts), today's date, and the conversation. Your device guard terms are
// replaced before anything leaves the desk.

import type { StudioKit } from "@/types";
import type { StudioChat, StudioImage } from "./chats";
import type { Content, Part } from "./gemini";

/** The kit's instructions plus when and where "now" is. A desk without a kit yet gets the short fallback. */
export function systemFor(kit: StudioKit | null | undefined, name: string, tz: string, now = new Date()): string {
  const when = new Intl.DateTimeFormat("en-AU", { timeZone: tz, weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit" }).format(now);
  const base =
    kit?.system ??
    `You are ${name}'s writing partner. Help them research and write LinkedIn and X posts in their voice. Never invent facts, figures, quotes or experiences.`;
  return `${base}\n\nIt is now ${when} (${tz}).`;
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Replace each guard term with "[redacted]" (the pipeline does the same with its blocklist before every call). */
export function redact(text: string, terms: string[]): string {
  let out = text;
  for (const t of terms) {
    const pattern = t.trim().split(/[\s-]+/).map(escape).join("[\\s-]+");
    if (pattern) out = out.replace(new RegExp(`(?<![\\w])${pattern}s?(?![\\w])`, "gi"), "[redacted]");
  }
  return out;
}

const dataOf = (img: StudioImage) => img.dataUrl.slice(img.dataUrl.indexOf(",") + 1);

/** The conversation for the model: the last 24 messages, with pictures from your last three messages that had any
 * (older ones are mentioned, not resent, to keep each call small). */
export function contentsFor(chat: StudioChat, terms: string[]): Content[] {
  const messages = chat.messages.filter((m) => !m.error && (m.text.trim() || m.images?.length || m.context)).slice(-24);
  const withPictures = new Set(
    messages
      .filter((m) => m.role === "user" && m.images?.length)
      .slice(-3)
      .map((m) => m.id),
  );
  const out: Content[] = [];
  for (const m of messages) {
    const parts: Part[] = [];
    const text = redact(m.text, terms);
    if (m.role === "user" && m.images?.length && !withPictures.has(m.id)) parts.push({ text: `[${m.images.length} picture(s) shared earlier]` });
    if (m.context) parts.push({ text: redact(m.context.body, terms) });
    if (text.trim()) parts.push({ text });
    if (m.role === "user" && withPictures.has(m.id)) for (const img of m.images ?? []) parts.push({ inlineData: { mimeType: img.mime, data: dataOf(img) } });
    if (!parts.length) continue;
    const role = m.role === "user" ? "user" : "model";
    // Gemini wants turns to alternate: fold two in a row from the same side into one.
    const prev = out[out.length - 1];
    if (prev && prev.role === role) prev.parts.push(...parts);
    else out.push({ role, parts });
  }
  return out;
}

/** The pictures in a chat, newest last (a visual's "use your photo" takes the last one). */
export const chatImages = (chat: StudioChat): StudioImage[] => chat.messages.flatMap((m) => (m.role === "user" ? (m.images ?? []) : []));

/** Everything a Studio post may draw on, for the live checks: what you wrote and the sources it found. */
export function evidenceOf(chat: StudioChat): string {
  const parts: string[] = [];
  for (const m of chat.messages) {
    if (m.role === "user") parts.push(m.text, m.context?.body ?? "");
    for (const s of m.sources ?? []) parts.push(s.title);
  }
  return parts.join("\n").slice(-12000);
}

/** `start`: what goes in the box when there's nothing yet to apply the action to (you finish the sentence). */
export type QuickAction = { label: string; prompt: string; start?: string; pick?: boolean };

/** Chips over the composer. What they offer depends on the chat: a start, a draft to rework, a shared post. */
export function quickActions(o: { hasPost: boolean; platform?: "linkedin" | "x" | null; shared: boolean; card: boolean }): QuickAction[] {
  if (o.shared)
    return [
      { label: "Why is it working?", prompt: "Why is this post working? The hook, the format, the angle, the timing." },
      { label: "My take", prompt: "Write my own take on this as a LinkedIn post." },
      { label: "Reply", prompt: "Write a reply to this post: short, adds something, not generic praise." },
      { label: "Quote-post", prompt: "Write an X quote-post for this." },
      { label: "Post ideas", prompt: "Give me post ideas inspired by this." },
    ];
  if (o.hasPost)
    return [
      { label: "Shorter", prompt: "Make it shorter." },
      { label: "New opening", prompt: "Give it a stronger opening line." },
      { label: "Funnier", prompt: "Make it funny: a joke about something specific and true, no clichés." },
      { label: "More me", prompt: "Make it sound more like me: plainer, more specific, less polished." },
      o.platform === "x" ? { label: "LinkedIn version", prompt: "Write the LinkedIn version." } : { label: "X version", prompt: "Write the X version." },
      { label: "Carousel", prompt: "Make a LinkedIn carousel from this." },
    ];
  return [
    ...(o.card ? [{ label: "Make it better", prompt: "Make this post better: sharper opening, more specific, same facts." }] : []),
    { label: "Post ideas", prompt: "Give me post ideas about this.", start: "Give me post ideas about " },
    { label: "LinkedIn post", prompt: "Write a LinkedIn post about this.", start: "Write a LinkedIn post about " },
    { label: "X post", prompt: "Write an X post about this.", start: "Write an X post about " },
    { label: "X thread", prompt: "Write an X thread about this.", start: "Write an X thread about " },
    { label: "Carousel", prompt: "Make a LinkedIn carousel from this.", start: "Make a LinkedIn carousel about " },
    { label: "Funny post", prompt: "Write a funny post about this: a joke about something specific and true, no clichés.", start: "Write a funny post about " },
    { label: "Research it", prompt: "Research this: what's new, what's true, and what people are saying. Cite sources.", start: "Research " },
  ];
}

/** Ideas to start from when a chat is empty. */
export const STARTERS: QuickAction[] = [
  { label: "What's everyone in tech talking about this week?", prompt: "What's everyone in tech and AI talking about this week, including the weird and funny stuff? Give me post ideas." },
  { label: "Turn a photo into a post", prompt: "Write a LinkedIn post about this picture.", pick: true },
  { label: "A carousel on something I know well", prompt: "Make a LinkedIn carousel about this.", start: "Make a LinkedIn carousel about " },
  { label: "A funny take on this week's tech news", prompt: "Write a funny X post about something that actually happened in tech this week. Search first." },
];
