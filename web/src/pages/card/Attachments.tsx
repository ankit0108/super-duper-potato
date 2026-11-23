import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Download, ImageIcon, ImagePlus, Plus, Share2, Trash2 } from "lucide-react";
import type { Attachment, Card } from "@/types";
import { downloadBlob } from "@/lib/visual/export";
import { dataUrlBytes, prepImage } from "@/lib/studio/images";
import { MAX_PICTURES, mediaItems, pictureLabel, sparePictures } from "@/lib/media";
import { newId } from "@/lib/storage";
import { useDesk } from "@/state/store";
import { Button } from "@/components/ui/Button";
import { canShareFiles } from "@/components/VisualViewer";

// Decoded here rather than fetched: the desk's content security policy doesn't let it fetch data: URLs.
async function toFile(dataUrl: string, name: string): Promise<File> {
  const type = /^data:([^;,]+)/.exec(dataUrl)?.[1] ?? "image/jpeg";
  return new File([dataUrlBytes(dataUrl).buffer as ArrayBuffer], name, { type });
}

function extFor(dataUrl: string): string {
  const type = /^data:([^;,]+)/.exec(dataUrl)?.[1] ?? "image/jpeg";
  return type === "image/png" ? "png" : type === "image/webp" ? "webp" : "jpg";
}

/** Each picture as a data URL from the data repo (or the demo); null when it can't be loaded. */
function useSrcs(items: Attachment[]): Record<string, string | null> {
  const loadMedia = useDesk((s) => s.loadMedia);
  const [srcs, setSrcs] = useState<Record<string, string | null>>({});
  const key = items.map((a) => a.path).join("|");
  useEffect(() => {
    let live = true;
    for (const path of key ? key.split("|") : []) {
      void loadMedia(path).then((src) => live && setSrcs((cur) => ({ ...cur, [path]: src })));
    }
    return () => {
      live = false;
    };
  }, [key, loadMedia]);
  return srcs;
}

function Thumb({ a, src, loaded, className, name }: { a: Attachment; src: string | null | undefined; loaded: boolean; className: string; name: string }) {
  return src ? (
    <img src={src} alt={a.alt || name} className={`${className} rounded-lg border border-border bg-surface-2 object-contain`} />
  ) : (
    <div className={`${className} flex items-center justify-center rounded-lg bg-surface-2 text-xs text-muted`}>{loaded ? "Not available" : "Loading…"}</div>
  );
}

function AltText({ a, onSave, readOnly }: { a: Attachment; onSave: (alt: string) => void; readOnly: boolean }) {
  const [value, setValue] = useState(a.alt ?? "");
  useEffect(() => setValue(a.alt ?? ""), [a.alt]);
  if (readOnly) return a.alt ? <p className="text-[12px] text-muted">Alt text: {a.alt}</p> : null;
  return (
    <label className="block text-[12px] text-muted">
      Alt text
      <textarea
        value={value}
        rows={2}
        maxLength={1000}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => value.trim() !== (a.alt ?? "").trim() && onSave(value)}
        placeholder="What the picture shows, for screen readers"
        className="mt-0.5 block w-full resize-y rounded-lg border border-border bg-surface px-2 py-1 text-[12.5px] text-text"
      />
    </label>
  );
}

/**
 * The pictures that go with the post: found in its sources, uploaded here, or shared in the Studio. Until it's
 * posted he can remove, move, add back or upload them (card.media), and edit each one's alt text; then download
 * them, or share them to the LinkedIn or X app on a phone. The credit for source pictures is in the first comment.
 */
export function Attachments({ card, slug }: { card: Card; slug: string }) {
  const act = useDesk((s) => s.act);
  const toast = useDesk((s) => s.toast);
  const uploadBlob = useDesk((s) => s.uploadBlob);
  const primeMedia = useDesk((s) => s.primeMedia);
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const items = card.attachments ?? [];
  const spare = sparePictures(card);
  const srcs = useSrcs([...items, ...spare]);
  const editable = card.status !== "posted";
  const full = items.length >= MAX_PICTURES;

  const send = (list: Attachment[], note?: string) =>
    act({ type: "card.media", card_id: card.id, items: mediaItems(list) }, note ? { toast: note } : undefined);
  const move = (i: number, by: number) => {
    const list = [...items];
    const [a] = list.splice(i, 1);
    list.splice(i + by, 0, a);
    send(list);
  };
  const upload = async (files: FileList | null) => {
    const room = MAX_PICTURES - items.length;
    const picked = [...(files ?? [])].filter((f) => /^image\/(jpeg|png|webp)$/.test(f.type)).slice(0, room);
    if (!picked.length) {
      if (files?.length) toast("bad", "Pick a JPEG, PNG or WebP picture.");
      return;
    }
    setUploading(true);
    try {
      const added: Attachment[] = [];
      for (const f of picked) {
        const img = await prepImage(f, f.name, 1600, 0.86);
        const path = `inbox/blobs/${card.id}_${newId("pic")}.jpg`;
        await uploadBlob(path, dataUrlBytes(img.dataUrl), "desk: picture for a post");
        primeMedia(path, img.dataUrl);
        added.push({ path, content_type: "image/jpeg", origin: "upload", width: img.width, height: img.height });
      }
      send([...items, ...added], added.length === 1 ? "Picture added." : `${added.length} pictures added.`);
    } catch {
      toast("bad", "Couldn't upload the picture. Check the connection and try again.");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const ready = items.map((a) => srcs[a.path]).filter((s): s is string => !!s);
  const name = (i: number, src: string) => `${slug}-${i + 1}.${extFor(src)}`;
  const share = async () => {
    try {
      await navigator.share({ files: await Promise.all(ready.map((s, i) => toFile(s, name(i, s)))) });
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") toast("bad", "Couldn't share the pictures: download them instead.");
    }
  };
  const download = async () => {
    for (const [i, s] of ready.entries()) downloadBlob((await toFile(s, name(i, s))) as Blob, name(i, s));
  };
  const shareable = typeof File !== "undefined" && canShareFiles([new File([""], "x.jpg", { type: "image/jpeg" })]);

  return (
    <section aria-label="Pictures" className="space-y-3 rounded-2xl border border-border bg-surface p-3">
      <h3 className="flex items-center gap-1.5 text-[13px] font-semibold">
        <ImageIcon className="size-4 text-accent" aria-hidden /> Pictures to post with it
        {!!items.length && <span className="font-normal text-muted">({items.length})</span>}
      </h3>
      {!items.length && <p className="text-[13px] text-muted">{editable ? "No pictures go with this post." : "Posted without pictures."}</p>}
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {items.map((a, i) => (
          <li key={a.path} className="space-y-1.5 rounded-xl border border-border p-2" aria-label={`Picture ${i + 1}: ${pictureLabel(a)}`}>
            <Thumb a={a} src={srcs[a.path]} loaded={a.path in srcs} className="h-40 w-full" name={`Picture ${i + 1}`} />
            <div className="flex items-center gap-1">
              <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium" title={a.caption ?? undefined}>
                {pictureLabel(a)}
              </span>
              {editable && (
                <>
                  <Button size="sm" variant="ghost" icon={<ArrowLeft className="size-4" />} aria-label={`Move picture ${i + 1} earlier`} disabled={i === 0} onClick={() => move(i, -1)} />
                  <Button size="sm" variant="ghost" icon={<ArrowRight className="size-4" />} aria-label={`Move picture ${i + 1} later`} disabled={i === items.length - 1} onClick={() => move(i, 1)} />
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Trash2 className="size-4" />}
                    aria-label={`Remove picture ${i + 1}`}
                    onClick={() => send(items.filter((b) => b.path !== a.path), "Picture removed. It's under \"Also available\" if you want it back.")}
                  />
                </>
              )}
            </div>
            {a.caption && <p className="line-clamp-2 text-[12px] text-muted">{a.caption}</p>}
            <AltText a={a} readOnly={!editable} onSave={(alt) => send(items.map((b) => (b.path === a.path ? { ...b, alt } : b)), "Alt text saved.")} />
          </li>
        ))}
      </ul>
      {editable && !!spare.length && (
        <div className="space-y-1.5">
          <h4 className="text-[12.5px] font-semibold text-muted">Also available</h4>
          <ul className="flex flex-wrap gap-2">
            {spare.map((a) => (
              <li key={a.path} className="w-32 space-y-1" aria-label={`Also available: ${pictureLabel(a)}`}>
                <Thumb a={a} src={srcs[a.path]} loaded={a.path in srcs} className="h-20 w-32" name={pictureLabel(a)} />
                <p className="truncate text-[11.5px] text-muted">{pictureLabel(a)}</p>
                <Button size="sm" variant="secondary" icon={<Plus className="size-4" />} disabled={full} onClick={() => send([...items, a], "Picture added.")} aria-label={`Add ${pictureLabel(a)}`}>
                  Add
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {editable && (
          <>
            <input
              ref={fileInput}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              multiple
              className="sr-only"
              aria-label="Upload a picture"
              data-testid="picture-upload"
              onChange={(e) => void upload(e.target.files)}
            />
            <Button size="sm" icon={<ImagePlus className="size-4" />} disabled={full || uploading} onClick={() => fileInput.current?.click()}>
              {uploading ? "Uploading…" : "Upload a picture"}
            </Button>
          </>
        )}
        {shareable && (
          <Button size="sm" variant="primary" icon={<Share2 className="size-4" />} onClick={() => void share()} disabled={!ready.length}>
            Share pictures
          </Button>
        )}
        <Button size="sm" icon={<Download className="size-4" />} onClick={() => void download()} disabled={!ready.length}>
          Download
        </Button>
      </div>
      {editable && full && <p className="text-[12px] text-muted">Four is the most X takes: remove one to add another.</p>}
      {editable && !!items.some((a) => a.origin === "source") && (
        <p className="text-[12px] text-muted">The pictures belong to their publishers: the first comment credits them.</p>
      )}
    </section>
  );
}
