import { useEffect, useState } from "react";
import type { Card, FormatName, Platform } from "@/types";
import { FORMAT_LABEL, REWRITE_CHIPS, pct } from "@/lib/format";
import { withoutHashtags } from "@/lib/hashtags";
import { editRatio } from "@/lib/text";
import { fromLocalInput, toLocalInput } from "@/lib/time";
import { safeUrl } from "@/lib/compose";
import { useTz } from "@/state/hooks";
import { Button, cx } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";

export type PostedPayload = { text: string; posts: string[] | null; post_url: string | null; posted_at: string; editing_seconds: number; with_visual: boolean };

export function PostedDialog({
  open,
  onClose,
  card,
  text,
  posts,
  tags = [],
  baseline,
  editingSeconds,
  visualLabel,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  card: Card;
  text: string;
  posts: string[];
  tags?: string[];
  baseline: string;
  editingSeconds: number;
  visualLabel?: string | null;
  onConfirm: (p: PostedPayload) => void;
}) {
  const tz = useTz();
  const [final, setFinal] = useState(text);
  const [withVisual, setWithVisual] = useState(true);
  const [url, setUrl] = useState("");
  const [when, setWhen] = useState(() => toLocalInput(new Date(), tz));
  const [minutes, setMinutes] = useState(Math.max(1, Math.round(editingSeconds / 60)));
  useEffect(() => {
    if (open) {
      setFinal(text);
      setWithVisual(true);
      setWhen(toLocalInput(new Date(), tz));
      setMinutes(Math.max(1, Math.round(editingSeconds / 60)));
    }
  }, [open, text, tz, editingSeconds]);
  const urlOk = !url || !!safeUrl(url);
  const ratio = baseline ? editRatio(baseline, withoutHashtags(final, tags)) : null;
  const isThread = card.format === "x_thread";
  const confirm = () => {
    const changedInDialog = final !== text;
    onConfirm({
      text: final,
      posts: isThread ? (changedInDialog ? final.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean) : posts) : null,
      post_url: url.trim() || null,
      posted_at: fromLocalInput(when, tz),
      editing_seconds: Math.max(0, Math.round(minutes * 60)),
      with_visual: !!visualLabel && withVisual,
    });
  };
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Mark as posted"
      description="Record what actually went out. The system learns from the difference."
      wide
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={confirm} disabled={!final.trim() || !urlOk}>
            Mark posted
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field
          label="Final text"
          htmlFor="posted-text"
          hint={isThread ? "Posts are separated by a blank line. If you changed anything in the app, paste the final version here." : "If you changed anything in the app, paste the final version here."}
        >
          <Textarea id="posted-text" value={final} onChange={(e) => setFinal(e.target.value)} minRows={6} />
        </Field>
        {ratio != null && (
          <p className="text-[13px] text-muted">
            Edit ratio against the draft: <Badge tone={ratio < 0.15 ? "ok" : ratio < 0.4 ? "warn" : "neutral"}>{pct(ratio)}</Badge>
          </p>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Post link (optional)" htmlFor="posted-url" error={!urlOk ? "That doesn't look like a web link." : undefined} hint="Makes metric matching exact.">
            <Input id="posted-url" type="url" inputMode="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
          </Field>
          <Field label="Posted at" htmlFor="posted-at">
            <Input id="posted-at" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
          </Field>
        </div>
        <Field label="Editing time (minutes)" htmlFor="posted-min" hint="Measured while this card was open and you were typing. Adjust if it's off.">
          <Input id="posted-min" type="number" min={0} max={600} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} className="w-28" />
        </Field>
        {visualLabel && (
          <Checkbox
            checked={withVisual}
            onChange={setWithVisual}
            label={`Posted with the visual (${visualLabel.toLowerCase()})`}
            description="So the system can compare how posts do with and without one."
          />
        )}
      </div>
    </Dialog>
  );
}

const TARGETS: Array<{ value: string; label: string; platform?: Platform; format?: FormatName }> = [
  { value: "", label: "Keep it on this platform" },
  { value: "linkedin:li_text", label: "Adapt for LinkedIn", platform: "linkedin", format: "li_text" },
  { value: "x:x_single", label: "Adapt for X: single post", platform: "x", format: "x_single" },
  { value: "x:x_thread", label: "Adapt for X: thread", platform: "x", format: "x_thread" },
];

export function RewriteDialog({
  open,
  onClose,
  card,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  card: Card;
  onConfirm: (p: { note: string; chips: string[]; target_platform?: Platform; target_format?: FormatName }) => void;
}) {
  const [chips, setChips] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [target, setTarget] = useState("");
  const [format, setFormat] = useState<FormatName | "">("");
  useEffect(() => {
    if (open) {
      setChips([]);
      setNote("");
      setTarget("");
      setFormat("");
    }
  }, [open]);
  const toggle = (c: string) => setChips((cs) => (cs.includes(c) ? cs.filter((x) => x !== c) : [...cs, c]));
  const t = TARGETS.find((x) => x.value === target);
  const xFormats: FormatName[] = ["x_single", "x_thread", "x_quote", "x_reply"];
  const confirm = () =>
    onConfirm({
      note: note.trim(),
      chips,
      ...(t?.platform && t.platform !== card.platform ? { target_platform: t.platform, target_format: t.format } : {}),
      ...(!t?.platform && format && format !== card.format ? { target_format: format } : {}),
    });
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Send back for a rewrite"
      description="The redraft arrives within 1–3 minutes. Your note also teaches the voice profile."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={confirm} disabled={!note.trim() && !chips.length && !target && !format}>
            Rewrite
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <div className="mb-2 text-[13px] font-medium">Quick asks</div>
          <div className="flex flex-wrap gap-1.5">
            {REWRITE_CHIPS.map((c) => (
              <button
                key={c}
                type="button"
                aria-pressed={chips.includes(c)}
                onClick={() => toggle(c)}
                className={cx(
                  "rounded-full border px-3 py-1 text-[13px] transition-colors",
                  chips.includes(c) ? "border-accent bg-accent-soft text-accent" : "border-border text-muted hover:text-text",
                )}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
        <Field label="Note" htmlFor="rw-note" hint='For example "lead with the benchmark number" or "less formal, more like how I talk".'>
          <Textarea id="rw-note" value={note} onChange={(e) => setNote(e.target.value)} minRows={3} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Platform" htmlFor="rw-target">
            <Select id="rw-target" value={target} onChange={(e) => setTarget(e.target.value)}>
              {TARGETS.filter((x) => x.platform !== card.platform || !x.platform).map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </Select>
          </Field>
          {card.platform === "x" && !target && (
            <Field label="Format" htmlFor="rw-format">
              <Select id="rw-format" value={format} onChange={(e) => setFormat(e.target.value as FormatName)}>
                <option value="">Keep {FORMAT_LABEL[card.format].toLowerCase()}</option>
                {xFormats
                  .filter((f) => f !== card.format)
                  .map((f) => (
                    <option key={f} value={f}>
                      {FORMAT_LABEL[f]}
                    </option>
                  ))}
              </Select>
            </Field>
          )}
        </div>
        {target && <p className="text-[13px] text-muted">A new card is created for the other platform; this one stays as it is.</p>}
      </div>
    </Dialog>
  );
}

export type CrosspostPayload = { target_platform: Platform; target_format: FormatName; mode: "both" | "switch"; note: string };

/**
 * A version of the post for the other platform. "Both" keeps this card; "switch" skips it as the wrong platform,
 * which teaches the ranking that the topic was right and the platform wasn't.
 */
export function CrosspostDialog({ open, onClose, card, onConfirm }: { open: boolean; onClose: () => void; card: Card; onConfirm: (c: CrosspostPayload) => void }) {
  const target: Platform = card.platform === "linkedin" ? "x" : "linkedin";
  const other = target === "x" ? "X" : "LinkedIn";
  const a = target === "x" ? "an" : "a";
  const long = (card.draft?.text ?? "").length > 600 || (card.draft?.posts?.length ?? 0) > 2;
  const [mode, setMode] = useState<"both" | "switch">("both");
  const [format, setFormat] = useState<FormatName>(target === "linkedin" ? "li_text" : long ? "x_thread" : "x_single");
  const [note, setNote] = useState("");
  const posted = card.status === "posted";
  useEffect(() => {
    if (open) {
      setMode("both");
      setFormat(target === "linkedin" ? "li_text" : long ? "x_thread" : "x_single");
      setNote("");
    }
  }, [open, target, long]);
  const options: Array<{ value: "both" | "switch"; label: string; help: string }> = [
    { value: "both", label: `Post it on both`, help: `Keep this ${card.platform === "x" ? "X" : "LinkedIn"} card and make ${a} ${other} version.` },
    ...(posted ? [] : [{ value: "switch" as const, label: `Move it to ${other} instead`, help: `This card is skipped as the wrong platform; the ranking learns that topics like it suit ${other}.` }]),
  ];
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`Make ${a} ${other} version`}
      description={`Rewritten for how ${other} works, not just trimmed. It arrives within 1–3 minutes.`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => onConfirm({ target_platform: target, target_format: format, mode, note: note.trim() })}>
            {mode === "switch" ? `Move to ${other}` : `Make the ${other} version`}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div role="radiogroup" aria-label="Where it goes" className="grid gap-2">
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={mode === o.value}
              onClick={() => setMode(o.value)}
              className={cx("rounded-xl border p-3 text-left transition-colors", mode === o.value ? "border-accent bg-accent-soft/50" : "border-border hover:bg-surface-2")}
            >
              <div className="text-[13.5px] font-semibold">{o.label}</div>
              <div className="mt-0.5 text-[13px] text-muted">{o.help}</div>
            </button>
          ))}
        </div>
        {target === "x" && (
          <Field label="Format on X" htmlFor="cp-format">
            <Select id="cp-format" value={format} onChange={(e) => setFormat(e.target.value as FormatName)}>
              <option value="x_single">{FORMAT_LABEL.x_single}</option>
              <option value="x_thread">{FORMAT_LABEL.x_thread}</option>
            </Select>
          </Field>
        )}
        <Field label="Anything to change for it? (optional)" htmlFor="cp-note" hint="For example “lead with the number” or “more casual”.">
          <Textarea id="cp-note" value={note} onChange={(e) => setNote(e.target.value)} minRows={2} maxLength={1000} />
        </Field>
      </div>
    </Dialog>
  );
}
