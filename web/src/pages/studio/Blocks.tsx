import { useState } from "react";
import { ImagePlus, Lightbulb, PenLine, Pencil, TriangleAlert } from "lucide-react";
import type { StudioIdea, StudioVisual } from "@/lib/studio/blocks";
import type { StudioImage } from "@/lib/studio/chats";
import { Badge, PlatformMark } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Field";
import { VISUAL_LABEL, VisualViewer } from "@/components/VisualViewer";
import type { StudioEnv } from "./env";

/** Post ideas: each one can be written up for LinkedIn or X with a tap. */
export function IdeasBlock({ ideas, onAsk, disabled }: { ideas: StudioIdea[]; onAsk: (prompt: string) => void; disabled: boolean }) {
  return (
    <section aria-label="Post ideas" className="space-y-2 rounded-2xl border border-border bg-surface p-3 shadow-sm">
      <h3 className="flex items-center gap-1.5 text-[13px] font-semibold">
        <Lightbulb className="size-4 text-accent" aria-hidden /> Post ideas
      </h3>
      <ol className="space-y-2">
        {ideas.map((idea, i) => (
          <li key={`${i}-${idea.title}`} className="rounded-xl border border-border p-2.5">
            <div className="flex items-start gap-2">
              {idea.platform && <PlatformMark platform={idea.platform} className="mt-0.5 shrink-0" />}
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-medium leading-snug">{idea.title}</p>
                {idea.angle && <p className="mt-0.5 text-[13px] text-muted">{idea.angle}</p>}
                {idea.why && <p className="mt-0.5 text-[12.5px] text-muted italic">{idea.why}</p>}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(idea.platform ? [idea.platform, idea.platform === "linkedin" ? "x" : "linkedin"] : ["linkedin", "x"]).map((p, j) => (
                <Button
                  key={p}
                  size="sm"
                  variant={j === 0 ? "soft" : "ghost"}
                  icon={<PenLine className="size-4" />}
                  disabled={disabled}
                  onClick={() => onAsk(`Write idea ${i + 1} (“${idea.title}”) as ${p === "linkedin" ? "a LinkedIn post" : "an X post"}.`)}
                >
                  {p === "linkedin" ? "Write for LinkedIn" : "Write for X"}
                </Button>
              ))}
              <Button size="sm" variant="ghost" icon={<ImagePlus className="size-4" />} disabled={disabled} onClick={() => onAsk(`Make a LinkedIn carousel for idea ${i + 1} (“${idea.title}”).`)}>
                Carousel
              </Button>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** A visual the Studio wrote and the desk draws: flip through it, edit the words, put your photo behind it. */
export function VisualBlock({
  visual,
  onChange,
  env,
  photo,
  onAsk,
  disabled,
}: {
  visual: StudioVisual;
  onChange: (v: StudioVisual) => void;
  env: StudioEnv;
  /** The last picture shared before this reply (what "use your photo" puts behind it). */
  photo: StudioImage | null;
  onAsk: (prompt: string) => void;
  disabled: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const withPhoto = visual.use_photo && !!photo && ["carousel", "stat", "quote"].includes(visual.kind);
  return (
    <section aria-label={VISUAL_LABEL[visual.kind]} className="space-y-3 rounded-2xl border border-border bg-surface p-3 shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-semibold">
          <ImagePlus className="size-4 text-accent" aria-hidden /> {VISUAL_LABEL[visual.kind]}
          <PlatformMark platform={visual.platform} />
          {withPhoto && <Badge tone="info">Your photo</Badge>}
        </h3>
        <Button size="sm" variant="ghost" icon={<Pencil className="size-4" />} onClick={() => setEditing((e) => !e)} aria-pressed={editing}>
          {editing ? "Close editor" : "Edit text"}
        </Button>
      </header>
      <VisualViewer
        visual={visual}
        platform={visual.platform}
        name={env.visualName(visual.platform)}
        accent={env.accent}
        image={withPhoto ? photo!.dataUrl : null}
        imageNote={withPhoto ? "Picture: your photo" : null}
        fileName={visual.title || "visual"}
        editing={editing}
        onCloseEditor={() => setEditing(false)}
        onEdit={(v) => {
          onChange({ ...visual, ...v, platform: visual.platform, use_photo: visual.use_photo });
          setEditing(false);
        }}
        actions={
          <Button size="sm" variant="soft" icon={<PenLine className="size-4" />} disabled={disabled} onClick={() => onAsk(`Write the ${visual.platform === "x" ? "X" : "LinkedIn"} post to go with this ${VISUAL_LABEL[visual.kind].toLowerCase()}.`)}>
            Write the post for it
          </Button>
        }
      />
      {photo && ["carousel", "stat", "quote"].includes(visual.kind) && (
        <Checkbox checked={visual.use_photo} onChange={(on) => onChange({ ...visual, use_photo: on })} label="Put your photo behind it" description="The last picture you shared, behind the cover, big number or quote. The words stay as written." />
      )}
    </section>
  );
}

/** A block that didn't come through as valid data: show what arrived and offer to try again. */
export function BrokenBlock({ name, raw, onRetry, disabled }: { name: string; raw: string; onRetry: () => void; disabled: boolean }) {
  return (
    <div className="space-y-2 rounded-xl border border-warn/30 bg-warn-soft px-3 py-2 text-[13px]">
      <p className="flex items-center gap-1.5 font-medium text-warn">
        <TriangleAlert className="size-4" aria-hidden /> This {name} didn't come through cleanly.
      </p>
      <details>
        <summary className="cursor-pointer text-muted">What arrived</summary>
        <pre className="mt-1 max-h-48 overflow-auto text-[12px] whitespace-pre-wrap">{raw}</pre>
      </details>
      <Button size="sm" onClick={onRetry} disabled={disabled}>
        Try again
      </Button>
    </div>
  );
}
