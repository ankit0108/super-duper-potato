import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, Copy, FileDown, ImageDown, Loader2, Share2 } from "lucide-react";
import type { Platform, Visual } from "@/types";
import { copyText } from "@/lib/compose";
import { layoutVisual } from "@/lib/visual/layout";
import { copyImage, downloadBlob, fileSlug, pdfBlob, pngBlob } from "@/lib/visual/export";
import { pageToSvg, svgDataUrl } from "@/lib/visual/svg";
import { useDesk } from "@/state/store";
import { Button, IconButton, cx } from "@/components/ui/Button";
import { Field, Input, Textarea } from "@/components/ui/Field";

export const VISUAL_LABEL: Record<Visual["kind"], string> = { carousel: "Carousel", flow: "Flowchart", compare: "Comparison", list: "Numbered list", stat: "Big number", quote: "Quote card", image: "AI image" };

/** Whether this browser can hand files to the phone's share sheet (Android Chrome can). */
export function canShareFiles(files: File[]): boolean {
  try {
    return typeof navigator !== "undefined" && !!navigator.canShare && navigator.canShare({ files });
  } catch {
    return false;
  }
}

/**
 * A drawn visual: the slides with paging, downloads (PNG, PDF for a carousel), copy, share and the text editor.
 * Used on a card's Visual panel and in the Studio. `image` is the picture behind it as a data URL (or null).
 */
export function VisualViewer({
  visual,
  platform,
  name,
  accent,
  image,
  imageLoading,
  imageNote,
  fileName,
  editing,
  onCloseEditor,
  onEdit,
  actions,
}: {
  visual: Visual;
  platform: Platform;
  name: string;
  accent?: string | null;
  image?: string | null;
  imageLoading?: boolean;
  imageNote?: string | null;
  fileName: string;
  editing: boolean;
  onCloseEditor: () => void;
  onEdit: (v: Visual) => void;
  /** More buttons for the row under the visual (the Studio's Save to board). */
  actions?: ReactNode;
}) {
  const toast = useDesk((s) => s.toast);
  const [page, setPage] = useState(0);
  const [working, setWorking] = useState(false);
  const pages = useMemo(() => layoutVisual(visual, { platform, name, accent, image: image ?? null }), [visual, platform, name, accent, image]);
  useEffect(() => setPage((p) => Math.min(p, Math.max(0, pages.length - 1))), [pages.length]);
  const current = pages[page];
  const svg = useMemo(() => (current ? pageToSvg(current) : ""), [current]);
  const slug = fileSlug(fileName);
  const carousel = visual.kind === "carousel";
  const shareable = useMemo(() => typeof File !== "undefined" && canShareFiles([new File([""], "x.png", { type: "image/png" })]), []);

  const run = async (fn: () => Promise<void>) => {
    setWorking(true);
    try {
      await fn();
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") toast("bad", e instanceof Error ? e.message : "That didn't work in this browser");
    } finally {
      setWorking(false);
    }
  };
  const downloadPng = () => run(async () => downloadBlob(await pngBlob(current), pages.length > 1 ? `${slug}-${page + 1}.png` : `${slug}.png`));
  const downloadPdf = () => run(async () => downloadBlob(await pdfBlob(pages), `${slug}.pdf`));
  const copyPng = () =>
    run(async () => {
      const ok = await copyImage(await pngBlob(current));
      toast(ok ? "ok" : "bad", ok ? "Image copied. Paste it into your post." : "This browser can't copy images: use Download PNG.");
    });
  const copyAlt = async () => {
    const ok = await copyText(visual.alt_text ?? "");
    toast(ok ? "ok" : "bad", ok ? "Alt text copied: add it to the image in the app." : "Couldn't copy the alt text.");
  };
  // The phone's share sheet: every slide as an image (LinkedIn takes up to 20, X up to 4).
  const share = () =>
    run(async () => {
      const limit = platform === "x" ? 4 : 20;
      const files: File[] = [];
      for (const [i, p] of pages.slice(0, limit).entries()) files.push(new File([await pngBlob(p)], pages.length > 1 ? `${slug}-${i + 1}.png` : `${slug}.png`, { type: "image/png" }));
      await navigator.share({ files, title: visual.title ?? undefined });
    });

  return (
    <>
      {current && (
        <figure className="space-y-2">
          <img
            src={svgDataUrl(svg)}
            alt={visual.alt_text || VISUAL_LABEL[visual.kind]}
            className="mx-auto w-full rounded-xl border border-border bg-white"
            style={{ aspectRatio: `${current.w} / ${current.h}`, maxHeight: platform === "linkedin" ? "34rem" : undefined, width: "auto" }}
          />
          {imageLoading && (
            <p className="flex items-center justify-center gap-1.5 text-xs text-muted">
              <Loader2 className="size-3.5 animate-spin" /> Loading the picture…
            </p>
          )}
          {imageNote && !imageLoading && <p className="text-center text-xs text-muted">{imageNote}</p>}
          {pages.length > 1 && (
            <figcaption className="flex items-center justify-center gap-2 text-[13px] text-muted">
              <IconButton size="sm" label="Previous slide" icon={<ChevronLeft className="size-4" />} onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} />
              <span aria-live="polite">
                Slide {page + 1} of {pages.length}
              </span>
              <IconButton size="sm" label="Next slide" icon={<ChevronRight className="size-4" />} onClick={() => setPage((p) => Math.min(pages.length - 1, p + 1))} disabled={page === pages.length - 1} />
            </figcaption>
          )}
        </figure>
      )}
      <div className="flex flex-wrap gap-2">
        {carousel && (
          <Button size="sm" variant="primary" icon={<FileDown className="size-4" />} onClick={downloadPdf} disabled={working}>
            Download PDF
          </Button>
        )}
        <Button size="sm" variant={carousel ? "secondary" : "primary"} icon={<ImageDown className="size-4" />} onClick={downloadPng} disabled={working}>
          {pages.length > 1 ? "Download this slide (PNG)" : "Download PNG"}
        </Button>
        {shareable && (
          <Button size="sm" icon={<Share2 className="size-4" />} onClick={share} disabled={working}>
            Share
          </Button>
        )}
        <Button size="sm" icon={<Copy className="size-4" />} onClick={copyPng} disabled={working}>
          Copy image
        </Button>
        <Button size="sm" variant="ghost" onClick={() => void copyAlt()} disabled={!visual.alt_text}>
          Copy alt text
        </Button>
        {actions}
      </div>
      <p className="text-xs text-muted">
        {platform === "linkedin"
          ? carousel
            ? "On LinkedIn, add a document to your post and upload the PDF: it shows as swipeable slides. Give it a short title."
            : "On LinkedIn, add it to your post as an image, with the alt text."
          : carousel
            ? "On X, attach up to four slides as images (download each), with the alt text."
            : "On X, attach it to your post as an image, with the alt text."}
      </p>
      {editing && <VisualEditor visual={visual} onSave={onEdit} onCancel={onCloseEditor} />}
    </>
  );
}

const ITEM_LABELS: Record<Visual["kind"], { title: string; body: string; many: string }> = {
  carousel: { title: "Slide heading", body: "Slide text", many: "Slides" },
  flow: { title: "Step", body: "What happens", many: "Steps" },
  compare: { title: "Column heading", body: "Points (one per line)", many: "Columns" },
  list: { title: "Item", body: "Detail", many: "Items" },
  stat: { title: "The figure", body: "What it measures", many: "The number" },
  quote: { title: "Who said it", body: "The quote", many: "The quote" },
  image: { title: "", body: "", many: "" },
};

export function VisualEditor({ visual, onSave, onCancel }: { visual: Visual; onSave: (v: Visual) => void; onCancel: () => void }) {
  const [draft, setDraft] = useState<Visual>(() => ({ ...visual, items: (visual.items ?? []).map((it) => ({ title: it.title ?? "", body: it.body ?? "" })) }));
  const labels = ITEM_LABELS[visual.kind];
  const setItem = (i: number, patch: { title?: string; body?: string }) => setDraft((d) => ({ ...d, items: (d.items ?? []).map((it, j) => (j === i ? { ...it, ...patch } : it)) }));
  return (
    <form
      className="space-y-3 rounded-xl bg-surface-2 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(draft);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Headline" htmlFor="v-title">
          <Input id="v-title" value={draft.title ?? ""} onChange={(e) => setDraft({ ...draft, title: e.target.value })} maxLength={200} />
        </Field>
        <Field label="Line under it" htmlFor="v-subtitle">
          <Input id="v-subtitle" value={draft.subtitle ?? ""} onChange={(e) => setDraft({ ...draft, subtitle: e.target.value })} maxLength={300} />
        </Field>
      </div>
      <fieldset className={cx("space-y-2", visual.kind === "image" && "hidden")}>
        <legend className="text-[13px] font-semibold">{labels.many}</legend>
        {(draft.items ?? []).map((it, i) => (
          <div key={i} className="grid gap-2 rounded-lg border border-border bg-surface p-2 sm:grid-cols-[14rem_1fr]">
            <Input aria-label={`${labels.title} ${i + 1}`} value={it.title ?? ""} onChange={(e) => setItem(i, { title: e.target.value })} maxLength={200} />
            <Textarea aria-label={`${labels.body} ${i + 1}`} value={it.body ?? ""} onChange={(e) => setItem(i, { body: e.target.value })} minRows={visual.kind === "compare" ? 3 : 1} maxLength={1000} />
          </div>
        ))}
      </fieldset>
      <Field label="Source line" htmlFor="v-caption">
        <Input id="v-caption" value={draft.caption ?? ""} onChange={(e) => setDraft({ ...draft, caption: e.target.value })} maxLength={300} />
      </Field>
      <Field label="Alt text" htmlFor="v-alt" hint="Read aloud by screen readers: what the image shows and its words.">
        <Textarea id="v-alt" value={draft.alt_text ?? ""} onChange={(e) => setDraft({ ...draft, alt_text: e.target.value })} minRows={2} maxLength={1500} />
      </Field>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary">
          Save visual
        </Button>
      </div>
    </form>
  );
}
