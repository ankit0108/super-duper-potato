// The pictures that go with a post: from the sources it was written from (pbs/source_media.py), uploaded on the
// desk, or shared in the Studio. The credit line mirrors source_media.credit_line, so the first comment is right
// on the desk before the pipeline has run.
import type { Attachment, Card, MediaItemIn } from "@/types";

/** X takes four pictures; LinkedIn more, but four read well on both. */
export const MAX_PICTURES = 4;

const DATA_KINDS = new Set(["chart", "graph", "diagram", "table"]);
const KIND_LABEL: Record<string, string> = {
  chart: "Chart",
  graph: "Graph",
  diagram: "Diagram",
  table: "Table",
  screenshot: "Screenshot",
  photo: "Photo",
  illustration: "Illustration",
  other: "Picture",
};

export function kindLabel(kind?: string | null): string {
  return KIND_LABEL[kind ?? "other"] ?? "Picture";
}

/** "Chart · Epoch AI", "Your upload", "Shared in the Studio". */
export function pictureLabel(a: Attachment): string {
  if (a.origin === "upload") return "Your upload";
  if (a.origin === "source") return [kindLabel(a.kind), a.publisher].filter(Boolean).join(" · ");
  return "Shared in the Studio";
}

/** "Chart: Epoch AI", "Images: The Verge, Epoch AI": who the source pictures going with the post belong to. */
export function creditLine(attachments: Attachment[] | null | undefined): string | null {
  const src = (attachments ?? []).filter((a) => a.origin === "source" && a.publisher);
  if (!src.length) return null;
  const pubs: string[] = [];
  for (const a of src) if (!pubs.includes(a.publisher!)) pubs.push(a.publisher!);
  const kinds = new Set(src.map((a) => a.kind ?? "other"));
  const only = (allowed: string[]) => [...kinds].every((k) => allowed.includes(k));
  const one = src.length === 1;
  const word = only(["chart", "graph"])
    ? one ? "Chart" : "Charts"
    : only(["diagram"])
      ? one ? "Diagram" : "Diagrams"
      : [...kinds].every((k) => DATA_KINDS.has(k))
        ? one ? "Figure" : "Figures"
        : one ? "Image" : "Images";
  return `${word}: ${pubs.join(", ")}`;
}

/** The draft with its first comment's credit line rewritten for these pictures. */
export function withCredit(card: Card, attachments: Attachment[]): Card["draft"] {
  const d = card.draft;
  if (!d || card.format === "x_reply") return d;
  const old = d.media_credit;
  let lines = (d.first_comment ?? "").split("\n");
  if (old) lines = lines.filter((ln) => ln.trim() !== old);
  let text = lines.join("\n").trimEnd();
  const next = creditLine(attachments);
  if (next) text = text ? `${text}\n${next}` : next;
  return { ...d, first_comment: text || null, media_credit: next };
}

/** Every picture the card can use: its pool (found in the sources, uploaded) plus what's attached now. */
export function picturePool(card: Card): Attachment[] {
  const out: Attachment[] = [];
  for (const a of [...(card.source_media ?? []), ...(card.attachments ?? [])]) {
    if (!out.some((b) => b.path === a.path)) out.push(a);
  }
  return out;
}

/** The pictures that could go with the post but don't now: one tap to add back. */
export function sparePictures(card: Card): Attachment[] {
  const on = new Set((card.attachments ?? []).map((a) => a.path));
  return picturePool(card).filter((a) => !on.has(a.path));
}

/** The card after a card.media event: the pictures in his order, with his alt text, uploads included. */
export function applyMedia(card: Card, items: MediaItemIn[]): Card {
  const pool = picturePool(card);
  const attachments: Attachment[] = [];
  for (const item of items.slice(0, MAX_PICTURES)) {
    if (attachments.some((a) => a.path === item.path)) continue;
    const known = pool.find((a) => a.path === item.path);
    const base: Attachment | null = known
      ? { ...known }
      : item.path.startsWith("inbox/blobs/")
        ? { path: item.path, content_type: "image/jpeg", origin: "upload" }
        : null;
    if (!base) continue;
    if (item.alt != null) base.alt = item.alt.trim() || null;
    attachments.push(base);
  }
  const sourceMedia = pool.map((a) => attachments.find((b) => b.path === a.path) ?? a);
  for (const a of attachments) if (!sourceMedia.some((b) => b.path === a.path)) sourceMedia.push(a);
  return { ...card, attachments, source_media: sourceMedia, draft: withCredit(card, attachments) };
}

/** The event items for a list of pictures (path and alt text). */
export function mediaItems(list: Attachment[]): MediaItemIn[] {
  return list.map((a) => ({ path: a.path, alt: a.alt ?? null }));
}
