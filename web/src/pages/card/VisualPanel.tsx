import { useEffect, useState } from "react";
import { ImagePlus, Loader2, Pencil, TriangleAlert } from "lucide-react";
import type { Card, ImagesStatus, Visual } from "@/types";
import { useDesk } from "@/state/store";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Checkbox, Field, Input, Select } from "@/components/ui/Field";
import { VISUAL_LABEL, VisualViewer } from "@/components/VisualViewer";
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
  const [editing, setEditing] = useState(false);
  const picture = useVisualImage(visual);
  const imagesOn = !!images?.available;
  const imagesSetUp = (images?.providers?.length ?? 0) > 0;
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
          {visual?.image && visual.kind !== "image" && <Badge tone="info">{visual.image.provider === "your photo" ? "Your photo" : "AI background"}</Badge>}
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
          <VisualViewer
            visual={visual}
            platform={card.platform}
            name={name}
            accent={accent}
            image={picture.src}
            imageLoading={picture.loading}
            imageNote={
              visual.image
                ? picture.src
                  ? visual.image.provider === "your photo"
                    ? "Picture: your photo"
                    : `Picture: AI-generated (${visual.image.provider}${visual.image.model ? `, ${visual.image.model.replace(/^@cf\/[^/]+\//, "")}` : ""})`
                  : "The picture couldn't be loaded; the words are drawn without it."
                : null
            }
            fileName={visual.title ?? card.title}
            editing={editing}
            onCloseEditor={() => setEditing(false)}
            onEdit={(v) => {
              onEdit(v);
              setEditing(false);
              toast("ok", "Visual updated.");
            }}
          />
          <details className="rounded-xl border border-border px-3 py-2">
            <summary className="cursor-pointer text-[13px] font-medium">Make a different one</summary>
            <div className="mt-3">{chooser}</div>
          </details>
        </>
      )}
    </section>
  );
}
