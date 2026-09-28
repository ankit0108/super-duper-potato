import { useRef, useState } from "react";
import { ArrowDown, ArrowUp, Combine, Copy, Pencil, Plus, Scissors, Trash2, Wand2 } from "lucide-react";
import type { Hook } from "@/types";
import { HOOK_LABEL, pct } from "@/lib/format";
import { diffWords, editRatio, splitSentences, xWeightedLength } from "@/lib/text";
import { splitIntoPosts } from "@/lib/thread";
import { copyText } from "@/lib/compose";
import type { LiveFlags } from "@/lib/guard";
import { useDesk } from "@/state/store";
import { Badge } from "@/components/ui/Badge";
import { Button, IconButton, cx } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Field";

// ---------------------------------------------------------------------------
// Counters
// ---------------------------------------------------------------------------

export function XRing({ used, limit }: { used: number; limit: number }) {
  const r = 9;
  const c = 2 * Math.PI * r;
  const ratio = Math.min(1, used / limit);
  const left = limit - used;
  const over = left < 0;
  const near = left <= 20;
  return (
    <span className="inline-flex items-center gap-1.5" aria-label={`${used} of ${limit} characters`} role="img">
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r={r} fill="none" stroke="var(--surface-3)" strokeWidth="2.5" />
        <circle
          cx="12"
          cy="12"
          r={r}
          fill="none"
          stroke={over ? "var(--bad)" : near ? "var(--warn)" : "var(--accent)"}
          strokeWidth="2.5"
          strokeDasharray={`${c * ratio} ${c}`}
          strokeLinecap="round"
          transform="rotate(-90 12 12)"
        />
      </svg>
      {near && <span className={cx("text-xs font-semibold tabular-nums", over ? "text-bad" : "text-warn")}>{left}</span>}
    </span>
  );
}

export function LinkedInCounter({ text, limit }: { text: string; limit: number }) {
  const n = text.length;
  return (
    <span className={cx("text-xs tabular-nums", n > limit ? "font-semibold text-bad" : "text-muted")}>
      {n.toLocaleString()} / {limit.toLocaleString()}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Opening / hooks
// ---------------------------------------------------------------------------

export function replaceOpening(text: string, hook: string): string {
  const t = text.replace(/^\s+/, "");
  const nl = t.indexOf("\n");
  if (nl > 0 && nl < 400) return hook + t.slice(nl);
  const sentences = splitSentences(t);
  if (sentences.length > 1) {
    const first = sentences[0];
    const at = t.indexOf(first);
    return hook + t.slice(at + first.length);
  }
  return t ? `${hook}\n\n${t}` : hook;
}

/** After he edits the opening that's in use: change it where it sits, or put the new one first. */
export function swapOpening(text: string, before: string, after: string): string {
  const t = text.replace(/^\s+/, "");
  if (before && t.startsWith(before)) return after + t.slice(before.length);
  if (before && t.includes(before)) return t.replace(before, after);
  return replaceOpening(text, after);
}

function HookRow({ hook, index, selected, onUse, onEdit }: { hook: Hook; index: number; selected: boolean; onUse: () => void; onEdit: (text: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(hook.text);
  const save = () => {
    const text = draft.replace(/\s+/g, " ").trim();
    if (text && text !== hook.text) onEdit(text);
    setEditing(false);
  };
  return (
    <li className={cx("flex items-start gap-2 rounded-xl border p-2.5", selected ? "border-accent bg-accent-soft/50" : "border-border")}>
      <div className="min-w-0 flex-1">
        <Badge tone="neutral" className="mb-1">
          {HOOK_LABEL[hook.type ?? "observation"] ?? hook.type}
        </Badge>
        {editing ? (
          <div className="space-y-1.5">
            <Textarea aria-label={`Edit opening ${index + 1}`} value={draft} onChange={(e) => setDraft(e.target.value)} minRows={2} maxLength={600} autoFocus />
            <div className="flex gap-1.5">
              <Button size="sm" variant="primary" onClick={save} disabled={!draft.trim()}>
                Save opening
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setDraft(hook.text); setEditing(false); }}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-[13.5px] leading-snug">{hook.text}</p>
        )}
      </div>
      {!editing && (
        <div className="flex shrink-0 items-center gap-0.5">
          <IconButton size="sm" label={`Edit opening ${index + 1}`} icon={<Pencil className="size-4" />} onClick={() => { setDraft(hook.text); setEditing(true); }} />
          <Button size="sm" variant={selected ? "soft" : "secondary"} onClick={onUse} aria-label={`Use opening ${index + 1}`}>
            {selected ? "Using" : "Use"}
          </Button>
        </div>
      )}
    </li>
  );
}

export function HooksPanel({ hooks, selected, onUse, onEdit, onAdd }: { hooks: Hook[]; selected: number | null; onUse: (i: number) => void; onEdit: (i: number, text: string) => void; onAdd: (text: string) => void }) {
  const [adding, setAdding] = useState(false);
  const [own, setOwn] = useState("");
  const add = () => {
    const text = own.replace(/\s+/g, " ").trim();
    if (!text) return;
    onAdd(text);
    setOwn("");
    setAdding(false);
  };
  return (
    <div className="space-y-2">
      <h3 className="text-[13px] font-semibold">Alternative openings</h3>
      {hooks.length > 0 && (
        <ul className="space-y-1.5">
          {hooks.map((h, i) => (
            <HookRow key={`${i}:${h.text}`} hook={h} index={i} selected={selected === i} onUse={() => onUse(i)} onEdit={(text) => onEdit(i, text)} />
          ))}
        </ul>
      )}
      {adding ? (
        <div className="space-y-1.5 rounded-xl border border-border p-2.5">
          <Textarea aria-label="Your own opening" value={own} onChange={(e) => setOwn(e.target.value)} minRows={2} maxLength={600} placeholder="The first line, in your words." autoFocus />
          <div className="flex gap-1.5">
            <Button size="sm" variant="primary" onClick={add} disabled={!own.trim()}>
              Add and use
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        hooks.length < 10 && (
          <Button size="sm" variant="ghost" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
            Write my own opening
          </Button>
        )
      )}
      <p className="text-xs text-muted">Edit any opening before or after using it. The openings you keep, edit and write teach the drafter your hook style.</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Feed preview and diff
// ---------------------------------------------------------------------------

export function FeedPreview({ text, fold }: { text: string; fold: number }) {
  const lines = text.split("\n");
  let visible = "";
  let count = 0;
  for (const line of lines) {
    if (count >= 3 || visible.length >= fold) break;
    visible += (visible ? "\n" : "") + line;
    count += 1;
  }
  if (visible.length > fold) visible = visible.slice(0, fold);
  const cut = visible.length < text.trim().length;
  return (
    <div className="rounded-xl border border-border bg-surface-2 p-3">
      <div className="mb-1 text-[11px] font-semibold tracking-wide text-muted uppercase">Before "see more" in the feed</div>
      <p className="draft-text text-[13.5px]">
        {visible}
        {cut && <span className="text-muted"> …see more</span>}
      </p>
    </div>
  );
}

export function DiffPanel({ before, after }: { before: string; after: string }) {
  const ops = diffWords(before, after);
  const ratio = editRatio(before, after);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-[13px] font-semibold">Your changes</h3>
        <Badge tone={ratio < 0.15 ? "ok" : ratio < 0.4 ? "warn" : "neutral"}>Edit ratio {pct(ratio)}</Badge>
      </div>
      <p className="draft-text rounded-xl border border-border bg-surface p-3 text-[13.5px]" aria-label="Word-level changes against the draft">
        {ops.length === 0 && <span className="text-muted">No text yet.</span>}
        {ops.map((o, i) =>
          o.op === "eq" ? (
            <span key={i}>{o.text}</span>
          ) : o.op === "ins" ? (
            <ins key={i} className="rounded bg-diff-add no-underline">
              {o.text}
            </ins>
          ) : (
            <del key={i} className="rounded bg-diff-del text-muted">
              {o.text}
            </del>
          ),
        )}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live checks
// ---------------------------------------------------------------------------

export function LiveChecks({ flags, hasGuardTerms }: { flags: LiveFlags; hasGuardTerms: boolean }) {
  const rows: Array<{ tone: "bad" | "warn"; title: string; items: string[] }> = [
    { tone: "bad", title: "Matches your device guard terms", items: flags.blocked },
    { tone: "warn", title: "Figures not found in the sources", items: flags.unsourced },
    { tone: "warn", title: "Reads like your own experience", items: flags.firstPerson },
    { tone: "warn", title: "Phrases you avoid", items: flags.avoid },
    { tone: "warn", title: "Engagement bait", items: flags.bait },
  ];
  const shown = rows.filter((r) => r.items.length);
  return (
    <div className="space-y-2" aria-live="polite">
      <h3 className="text-[13px] font-semibold">Live checks</h3>
      {flags.platform.length > 0 && (
        <div className="rounded-xl border border-info/30 bg-info-soft px-3 py-2 text-[13px]">
          <div className="font-medium text-info">Platform tips</div>
          <ul className="mt-0.5 list-disc pl-4 text-text">
            {flags.platform.map((it) => (
              <li key={it}>{it}</li>
            ))}
          </ul>
        </div>
      )}
      {shown.length === 0 ? (
        <p className="text-[13px] text-ok">Nothing flagged in the current text.</p>
      ) : (
        shown.map((r) => (
          <div key={r.title} className={cx("rounded-xl border px-3 py-2 text-[13px]", r.tone === "bad" ? "border-bad/30 bg-bad-soft" : "border-warn/30 bg-warn-soft")}>
            <div className={cx("font-medium", r.tone === "bad" ? "text-bad" : "text-warn")}>{r.title}</div>
            <ul className="mt-0.5 list-disc pl-4 text-text">
              {r.items.map((it) => (
                <li key={it}>{it}</li>
              ))}
            </ul>
          </div>
        ))
      )}
      {!hasGuardTerms && <p className="text-xs text-muted">Tip: add your employer and client names in Settings → Guard terms to check them live on this device.</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Editors
// ---------------------------------------------------------------------------

export function LinkedInEditor({ value, onChange, limit, fold, suffix }: { value: string; onChange: (v: string) => void; limit: number; fold: number; suffix?: string }) {
  const counted = suffix ? `${value.trimEnd()}\n\n${suffix}` : value;
  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-border bg-surface focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15">
        <Textarea
          aria-label="LinkedIn post"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          minRows={10}
          className="border-0 bg-transparent text-[15px] shadow-none focus:ring-0"
        />
        <div className="flex items-center justify-end border-t border-border px-3 py-1.5">
          <LinkedInCounter text={counted} limit={limit} />
        </div>
      </div>
      <FeedPreview text={value} fold={fold} />
    </div>
  );
}

export function XPostEditor({ value, onChange, limit, label, minRows = 4, footer, suffix }: { value: string; onChange: (v: string) => void; limit: number; label: string; minRows?: number; footer?: React.ReactNode; suffix?: string }) {
  // The chosen hashtags count too: they're added after the text.
  const used = xWeightedLength(suffix ? `${value.trimEnd()} ${suffix}` : value);
  return (
    <div className={cx("rounded-2xl border bg-surface focus-within:ring-2 focus-within:ring-accent/15", used > limit ? "border-bad/50" : "border-border focus-within:border-accent")}>
      <Textarea aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} minRows={minRows} className="border-0 bg-transparent text-[15px] shadow-none focus:ring-0" />
      <div className="flex items-center justify-between gap-2 border-t border-border px-3 py-1.5">
        <div className="flex items-center gap-1">{footer}</div>
        <XRing used={used} limit={limit} />
      </div>
    </div>
  );
}

export function ThreadEditor({ posts, onChange, limit, min, max, firstSuffix }: { posts: string[]; onChange: (p: string[]) => void; limit: number; min: number; max: number; firstSuffix?: string }) {
  const refs = useRef<Array<HTMLTextAreaElement | null>>([]);
  const [numbering, setNumbering] = useState(false);
  const toast = useDesk((s) => s.toast);
  const set = (i: number, v: string) => onChange(posts.map((p, j) => (j === i ? v : p)));
  const move = (i: number, d: -1 | 1) => {
    const next = [...posts];
    const j = i + d;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };
  const remove = (i: number) => onChange(posts.length > 1 ? posts.filter((_, j) => j !== i) : [""]);
  const merge = (i: number) => {
    if (i + 1 >= posts.length) return;
    const next = [...posts];
    next.splice(i, 2, `${posts[i].trimEnd()} ${posts[i + 1].trimStart()}`.trim());
    onChange(next);
  };
  const split = (i: number) => {
    const el = refs.current[i];
    const at = el?.selectionStart ?? Math.floor(posts[i].length / 2);
    const a = posts[i].slice(0, at).trim();
    const b = posts[i].slice(at).trim();
    if (!a || !b) return;
    const next = [...posts];
    next.splice(i, 1, a, b);
    onChange(next);
  };
  const autoSplit = () => onChange(splitIntoPosts(posts.join("\n\n"), limit - (numbering ? 6 : 0)));
  const label = (i: number) => (i === 0 && firstSuffix ? ` ${firstSuffix}` : "") + (numbering ? `\n\n${i + 1}/${posts.length}` : "");
  const copyOne = async (i: number) => {
    const ok = await copyText(posts[i] + label(i));
    toast(ok ? "ok" : "bad", ok ? `Post ${i + 1} copied` : "Couldn't copy");
  };
  const outOfRange = posts.length < min || posts.length > max;
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={cx("text-[13px]", outOfRange ? "text-warn" : "text-muted")}>
          {posts.length} post{posts.length === 1 ? "" : "s"} {outOfRange && `· aim for ${min}–${max}`}
        </span>
        <div className="flex items-center gap-1">
          <label className="mr-2 inline-flex items-center gap-1.5 text-[13px] text-muted">
            <input type="checkbox" checked={numbering} onChange={(e) => setNumbering(e.target.checked)} className="accent-[var(--accent)]" />
            Add 1/n when copying
          </label>
          <Button size="sm" variant="ghost" icon={<Wand2 className="size-4" />} onClick={autoSplit}>
            Auto-split
          </Button>
        </div>
      </div>
      <ol className="space-y-2.5">
        {posts.map((p, i) => (
          <li key={i} className="relative pl-7">
            <span className="absolute top-3 left-0 flex size-5 items-center justify-center rounded-full bg-surface-3 text-[11px] font-semibold text-muted">{i + 1}</span>
            <div className={cx("rounded-2xl border bg-surface", xWeightedLength(p + label(i)) > limit ? "border-bad/50" : "border-border")}>
              <Textarea
                ref={(el) => {
                  refs.current[i] = el;
                }}
                aria-label={`Post ${i + 1} of ${posts.length}`}
                value={p}
                onChange={(e) => set(i, e.target.value)}
                minRows={2}
                className="border-0 bg-transparent text-[15px] shadow-none focus:ring-0"
              />
              <div className="flex items-center justify-between gap-1 border-t border-border px-2 py-1">
                <div className="flex items-center">
                  <IconButton size="sm" label="Copy this post" icon={<Copy className="size-4" />} onClick={() => void copyOne(i)} />
                  <IconButton size="sm" label="Split at cursor" icon={<Scissors className="size-4" />} onClick={() => split(i)} />
                  <IconButton size="sm" label="Merge with next" icon={<Combine className="size-4" />} onClick={() => merge(i)} disabled={i === posts.length - 1} />
                  <IconButton size="sm" label="Move up" icon={<ArrowUp className="size-4" />} onClick={() => move(i, -1)} disabled={i === 0} />
                  <IconButton size="sm" label="Move down" icon={<ArrowDown className="size-4" />} onClick={() => move(i, 1)} disabled={i === posts.length - 1} />
                  <IconButton size="sm" label="Delete post" icon={<Trash2 className="size-4" />} onClick={() => remove(i)} />
                </div>
                <XRing used={xWeightedLength(p + label(i))} limit={limit} />
              </div>
            </div>
          </li>
        ))}
      </ol>
      <Button size="sm" variant="secondary" icon={<Plus className="size-4" />} onClick={() => onChange([...posts, ""])} disabled={posts.length >= 15}>
        Add post
      </Button>
    </div>
  );
}

export function numbered(posts: string[]): string[] {
  return posts.map((p, i) => (posts.length > 1 ? `${p}\n\n${i + 1}/${posts.length}` : p));
}
