import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Copy, FileDown, ImageDown, ImagePlus, Loader2, Pencil, TriangleAlert } from "lucide-react";
import type { Card, ImagesStatus, Visual } from "@/types";
import { copyText } from "@/lib/compose";
import { layoutVisual } from "@/lib/visual/layout";
import { copyImage, downloadBlob, fileSlug, pdfBlob, pngBlob } from "@/lib/visual/export";
import { pageToSvg, svgDataUrl } from "@/lib/visual/svg";
import { useDesk } from "@/state/store";
import { Badge } from "@/components/ui/Badge";
import { Button, IconButton, cx } from "@/components/ui/Button";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Link } from "@/lib/router";

export type VisualChoice = Visual["kind"] | "auto";

export const VISUAL_KINDS: Array<{ value: VisualChoice; label: string; help: string }> = [
  { value: "auto", label: "Let it choose", help: "The kind that suits this post" },
  { value: "carousel", label: "Carousel", help: "4 to 8 slides; on LinkedIn, a document post" },
  { value: "flow", label: "Flowchart", help: "A process, step by step" },
  { value: "compare", label: "Comparison", help: "Two columns: before and after, demo and production" },
  { value: "list", label: "Numbered list", help: "Tips or lessons" },
  { value: "stat", label: "Big number", help: "One figure that carries the post" },
  { value: "quote", label: "Quote card", help: "A line from a source" },
  { value: "image", label: "AI image", help: "An illustration made by an image model, with no words in it" },
];
export const VISUAL_LABEL: Record<Visual["kind"], string> = { carousel: "Carousel", flow: "Flowchart", compare: "Comparison", list: "Numbered list", stat: "Big number", quote: "Quote card", image: "AI image" };
/** Kinds that can have an AI image behind them ("auto" may pick one of them). */
const BACKGROUND_KINDS: VisualChoice[] = ["auto", "carousel", "stat", "quote"];

/** The visual's AI image as a data URL, once loaded (null while loading, or if there's none). */
function useVisualImage(visual: Visual | null): { src: string | null; loading: boolean } {
  const loadMedia = useDesk((s) => s.loadMedia);
  const path = visual?.image?.path ?? null;
  const [state, setState] = useState<{ path: string | null; src: string | null }>({ path: null, src: null });
  useEffect(() => {
    let live = true;
    if (!path) return;
    void loadMedia(path).then((src) => live && setState({ path, src }));
    return () => {
      live = false;
    };
  }, [path, loadMedia]);
  const src = state.path === path ? state.src : null;
  return { src, loading: !!path && state.path !== path };
}

/**
 * A visual for the post: a carousel, flowchart, comparison, list, big number, quote card or AI image, written from
 * the post and its sources and drawn here. An image model only makes pictures (an illustration, or a background
 * behind a carousel cover, big number or quote card); every word is drawn here and can be edited. Download it as
 * PNG or, for a carousel, a PDF to post on LinkedIn as a document. What he keeps and posts is learned from.
 */
export function VisualPanel({
  card,
  visual,
  busy,
  canRequest,
  name,
  accent,
  images,
  onRequest,
  onEdit,
}: {
  card: Card;
  visual: Visual | null;
  busy: boolean;
  canRequest: boolean;
  name: string;
  accent?: string | null;
  images?: ImagesStatus | null;
  onRequest: (kind: VisualChoice, note: string, aiBackground: boolean) => void;
  onEdit: (v: Visual) => void;
}) {
  const toast = useDesk((s) => s.toast);
  const [kind, setKind] = useState<VisualChoice>("auto");
  const [note, setNote] = useState("");
  const [background, setBackground] = useState(false);
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState(false);
  const [working, setWorking] = useState(false);
  const picture = useVisualImage(visual);
  const imagesOn = !!images?.available;
  const imagesSetUp = (images?.providers?.length ?? 0) > 0;
  const pages = useMemo(
    () => (visual ? layoutVisual(visual, { platform: card.platform, name, accent, image: picture.src }) : []),
    [visual, card.platform, name, accent, picture.src],
  );
  useEffect(() => setPage((p) => Math.min(p, Math.max(0, pages.length - 1))), [pages.length]);
  const current = pages[page];
  const svg = useMemo(() => (current ? pageToSvg(current) : ""), [current]);
  const slug = fileSlug(visual?.title ?? card.title);
  const carousel = visual?.kind === "carousel";

  const run = async (fn: () => Promise<void>) => {
    setWorking(true);
    try {
      await fn();
    } catch (e) {
      toast("bad", e instanceof Error ? e.message : "That didn't work in this browser");
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
    const ok = await copyText(visual?.alt_text ?? "");
    toast(ok ? "ok" : "bad", ok ? "Alt text copied: add it to the image in the app." : "Couldn't copy the alt text.");
  };
  const wantsPicture = kind === "image" || (background && BACKGROUND_KINDS.includes(kind));
  const request = () => {
    onRequest(kind, note.trim(), background && BACKGROUND_KINDS.includes(kind));
    setNote("");
  };

  const chooser = (
    <div className="space-y-2">
      <div className="grid gap-2 sm:grid-cols-[12rem_1fr_auto] sm:items-end">
        <Field label={visual ? "Another kind" : "Kind"} htmlFor="visual-kind">
          <Select id="visual-kind" value={kind} onChange={(e) => setKind(e.target.value as VisualChoice)}>
            {VISUAL_KINDS.map((k) => (
              <option key={k.value} value={k.value} disabled={k.value === "image" && !imagesOn}>
                {k.label}
                {k.value === "image" && !imagesOn ? (imagesSetUp ? " (none left today)" : " (set up first)") : ""}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Anything to say? (optional)" htmlFor="visual-note">
          <Input id="visual-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} placeholder={kind === "image" ? "For example “a warehouse at dawn, calm”" : "For example “five steps, one per slide”"} />
        </Field>
        <Button variant={visual ? "secondary" : "primary"} icon={<ImagePlus className="size-4" />} onClick={request} disabled={!canRequest || busy || (wantsPicture && !imagesOn)}>
          {visual ? "Make another" : "Create visual"}
        </Button>
      </div>
      {BACKGROUND_KINDS.includes(kind) && (
        <Checkbox
          checked={background && imagesOn}
          onChange={(v) => setBackground(v)}
          label="Add an AI background"
          description={imagesOn ? "A picture behind the cover, big number or quote; the words stay exactly as written." : imagesSetUp ? "Not available today (below)." : "Needs an image service first (below)."}
        />
      )}
      {!imagesOn && imagesSetUp && (kind === "image" || BACKGROUND_KINDS.includes(kind)) && (
        <p className="text-xs text-muted">
          Today's AI images are used up ({images?.used_today ?? 0} of {images?.daily_limit ?? 0}, or the service's free allowance); they're back tomorrow. Settings → AI images changes the limit.
        </p>
      )}
      {!imagesOn && !imagesSetUp && (kind === "image" || BACKGROUND_KINDS.includes(kind)) && (
        <p className="text-xs text-muted">
          AI images need an image service: add the free <code>CLOUDFLARE_ACCOUNT_ID</code> and <code>CLOUDFLARE_API_TOKEN</code> secrets (docs/SETUP.md, “AI images”), then{" "}
          <Link to="/system" className="text-accent hover:underline">
            run the doctor
          </Link>
          .
        </p>
      )}
    </div>
  );

  return (
    <section aria-label="Visual" className="space-y-3 rounded-2xl border border-border bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-semibold">
          <ImagePlus className="size-4 text-accent" aria-hidden /> Visual
          {visual && <Badge tone="neutral">{VISUAL_LABEL[visual.kind]}</Badge>}
          {visual?.image && visual.kind !== "image" && <Badge tone="info">AI background</Badge>}
        </h3>
        {visual && !busy && (
          <Button size="sm" variant="ghost" icon={<Pencil className="size-4" />} onClick={() => setEditing((e) => !e)} aria-pressed={editing}>
            {editing ? "Close editor" : "Edit text"}
          </Button>
        )}
      </div>

      {busy ? (
        <p className="flex items-center gap-2 text-[13px] text-accent">
          <Loader2 className="size-4 animate-spin" /> {card.work?.visual_kind === "image" || card.work?.ai_background ? "Making the picture and drawing the visual from this post. Takes 1–3 minutes." : "Drawing the visual from this post and its sources. Takes 1–3 minutes."}
        </p>
      ) : !visual ? (
        <>
          <p className="text-[13px] text-muted">A carousel, flowchart, one big number or an AI image gets more people to stop and read. It's written from this post and its sources and drawn here, in your style: every word can be edited, and pictures never contain words.</p>
          {chooser}
        </>
      ) : (
        <>
          {!!visual.unsourced?.length && (
            <p className="flex items-start gap-1.5 rounded-xl bg-warn-soft px-3 py-2 text-[13px] text-warn">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                Check {visual.unsourced.length === 1 ? "this figure" : "these figures"}: {visual.unsourced.join(", ")}. The sources don't contain {visual.unsourced.length === 1 ? "it" : "them"}.
              </span>
            </p>
          )}
          {current && (
            <figure className="space-y-2">
              <img
                src={svgDataUrl(svg)}
                alt={visual.alt_text || VISUAL_LABEL[visual.kind]}
                className="mx-auto w-full rounded-xl border border-border bg-white"
                style={{ aspectRatio: `${current.w} / ${current.h}`, maxHeight: card.platform === "linkedin" ? "34rem" : undefined, width: "auto" }}
              />
              {picture.loading && (
                <p className="flex items-center justify-center gap-1.5 text-xs text-muted">
                  <Loader2 className="size-3.5 animate-spin" /> Loading the picture…
                </p>
              )}
              {visual.image && !picture.loading && (
                <p className="text-center text-xs text-muted">
                  {picture.src ? `Picture: AI-generated (${visual.image.provider}${visual.image.model ? `, ${visual.image.model.replace(/^@cf\/[^/]+\//, "")}` : ""})` : "The picture couldn't be loaded; the words are drawn without it."}
                </p>
              )}
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
            <Button size="sm" icon={<Copy className="size-4" />} onClick={copyPng} disabled={working}>
              Copy image
            </Button>
            <Button size="sm" variant="ghost" onClick={() => void copyAlt()} disabled={!visual.alt_text}>
              Copy alt text
            </Button>
          </div>
          <p className="text-xs text-muted">
            {card.platform === "linkedin"
              ? carousel
                ? "On LinkedIn, add a document to your post and upload the PDF: it shows as swipeable slides. Give it a short title."
                : "On LinkedIn, add it to your post as an image, with the alt text."
              : carousel
                ? "On X, attach up to four slides as images (download each), with the alt text."
                : "On X, attach it to your post as an image, with the alt text."}
          </p>
          {editing && <VisualEditor visual={visual} onSave={(v) => { onEdit(v); setEditing(false); toast("ok", "Visual updated."); }} onCancel={() => setEditing(false)} />}
          <details className="rounded-xl border border-border px-3 py-2">
            <summary className="cursor-pointer text-[13px] font-medium">Make a different one</summary>
            <div className="mt-3">{chooser}</div>
          </details>
        </>
      )}
    </section>
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

function VisualEditor({ visual, onSave, onCancel }: { visual: Visual; onSave: (v: Visual) => void; onCancel: () => void }) {
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
