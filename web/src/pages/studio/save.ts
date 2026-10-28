// Save to board: a Studio post (with its pictures and visual) becomes a card in Today's picks. The pictures go to
// inbox/blobs/ first; the studio.save event tells the pipeline to make the card (pbs/studio.py) and the overlay
// shows it at once.
import type { StudioKit } from "@/types";
import { newId } from "@/lib/storage";
import type { StudioPost, StudioVisual } from "@/lib/studio/blocks";
import type { StudioImage } from "@/lib/studio/chats";
import { dataUrlBytes } from "@/lib/studio/images";
import { useDesk } from "@/state/store";

export async function saveToBoard(o: {
  post: StudioPost;
  hashtags: string[];
  images: StudioImage[];
  visual: StudioVisual | null;
  /** The picture behind the visual, when it uses one. */
  photo: StudioImage | null;
  evidence: string;
  model: string | null;
  kit: StudioKit | null;
}): Promise<string> {
  const { uploadBlob, primeMedia, act } = useDesk.getState();
  const cardId = newId("crd");
  const pictures = [...o.images];
  if (o.photo && !pictures.some((p) => p.id === o.photo!.id)) pictures.push(o.photo);
  const uploaded: Array<{ path: string; width: number; height: number }> = [];
  for (const [i, img] of pictures.entries()) {
    const path = `inbox/blobs/${cardId}_${i + 1}.jpg`;
    await uploadBlob(path, dataUrlBytes(img.dataUrl), "desk: studio picture");
    primeMedia(path, img.dataUrl);
    uploaded.push({ path, width: img.width, height: img.height });
  }
  const p = o.post;
  const v = o.visual;
  act(
    {
      type: "studio.save",
      card_id: cardId,
      platform: p.platform,
      format: p.format,
      title: (p.format === "x_thread" ? p.posts[0] : p.text)?.split("\n")[0]?.slice(0, 200) ?? "",
      text: p.format === "x_thread" ? "" : p.text,
      posts: p.format === "x_thread" ? p.posts.filter((t) => t.trim()) : [],
      hooks: p.hooks,
      hashtags: o.hashtags,
      first_comment: p.first_comment,
      pillar: p.pillar,
      post_type: p.post_type,
      sources: p.sources.slice(0, 12),
      images: uploaded,
      visual: v
        ? {
            kind: v.kind,
            title: v.title ?? "",
            subtitle: v.subtitle ?? null,
            caption: v.caption ?? null,
            alt_text: v.alt_text ?? "",
            items: (v.items ?? []).map((it) => ({ title: it.title ?? "", body: it.body ?? "" })),
            photo: o.photo ? pictures.findIndex((x) => x.id === o.photo!.id) : null,
          }
        : null,
      evidence: o.evidence.slice(-12000),
      model: o.model,
      kit_version: o.kit?.version ?? null,
    },
    { toast: "Saved to the board: it's in Today's picks." },
  );
  return cardId;
}
