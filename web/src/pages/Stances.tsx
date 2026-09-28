import { useMemo, useState } from "react";
import { Archive, ExternalLink, Plus, Sparkles } from "lucide-react";
import type { Stance } from "@/types";
import { safeUrl } from "@/lib/compose";
import { newId } from "@/lib/storage";
import { formatDate } from "@/lib/time";
import { useDesk } from "@/state/store";
import { useTz } from "@/state/hooks";
import { Badge } from "@/components/ui/Badge";
import { Button, cx } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Empty } from "@/components/ui/Feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Tabs } from "@/components/ui/Tabs";

type Tier = "world" | "india" | "bihar" | "other" | "archived";
const TIERS: Array<{ value: Tier; label: string }> = [
  { value: "bihar", label: "Bihar" },
  { value: "india", label: "India" },
  { value: "world", label: "World" },
  { value: "other", label: "Other" },
  { value: "archived", label: "Archived" },
];

function StanceCard({ stance }: { stance: Stance }) {
  const act = useDesk((s) => s.act);
  const pending = useDesk((s) => s.pending.stances.has(stance.id));
  const tz = useTz();
  const chosen = stance.chosen;
  const saved = chosen?.custom_text ?? "";
  const [own, setOwn] = useState(saved);
  const [writing, setWriting] = useState(false);
  const picked = !saved ? (stance.positions ?? []).find((p) => p.key === chosen?.position_key) : undefined;
  const pick = (key: string) => {
    act({ type: "stance.upsert", stance_id: stance.id, chosen_key: key, custom_text: null }, { toast: "Stance saved." });
    setWriting(false);
  };
  const saveOwn = () => {
    if (!own.trim()) return;
    act({ type: "stance.upsert", stance_id: stance.id, chosen_key: null, custom_text: own.trim() }, { toast: "Your stance is saved in your own words." });
    setWriting(false);
  };
  const startWriting = () => {
    setOwn(saved);
    setWriting(true);
  };
  const clear = () => act({ type: "stance.upsert", stance_id: stance.id, clear_choice: true }, { toast: "Stance cleared." });
  const bg = safeUrl(stance.sources?.[0]?.url);
  return (
    <article className="rounded-2xl border border-border bg-surface p-4" aria-label={`Stance: ${stance.issue}`}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 font-semibold">{stance.issue}</h3>
        <div className="flex shrink-0 items-center gap-1.5">
          {pending && (
            <Badge tone="neutral" title="Saved on this device; the pipeline picks it up on its next run">
              Saved · syncs on the next run
            </Badge>
          )}
          {chosen ? <Badge tone="ok">Stance recorded</Badge> : <Badge tone="warn">No stance yet</Badge>}
        </div>
      </div>
      {stance.context && <p className="mt-1 text-[13.5px] text-muted">{stance.context}</p>}
      {(saved || picked) && !writing && (
        <div className="mt-3 rounded-xl border border-accent/40 bg-accent-soft/40 p-3">
          <div className="text-[12px] font-semibold tracking-wide text-accent uppercase">Your stance</div>
          <p className="mt-0.5 text-[14px] whitespace-pre-line">{saved || `${picked!.label}: ${picked!.text}`}</p>
        </div>
      )}
      {(stance.positions ?? []).length > 0 && (
        <div role="radiogroup" aria-label={`Positions on ${stance.issue}`} className="mt-3 grid gap-2 md:grid-cols-2">
          {(stance.positions ?? []).map((p) => {
            const selected = chosen?.position_key === p.key && !saved;
            return (
              <button
                key={p.key}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => pick(p.key)}
                className={cx(
                  "rounded-xl border p-3 text-left transition-colors",
                  selected ? "border-accent bg-accent-soft/50" : "border-border hover:border-border-strong hover:bg-surface-2",
                )}
              >
                <div className="text-[13.5px] font-semibold">{p.label}</div>
                <div className="mt-0.5 text-[13px] text-muted">{p.text}</div>
              </button>
            );
          })}
        </div>
      )}
      <div className="mt-3">
        {writing ? (
          <div className="space-y-2">
            <Textarea aria-label="Your own stance" value={own} onChange={(e) => setOwn(e.target.value)} minRows={2} maxLength={1000} placeholder="Your view in one to three lines, in your own words." autoFocus />
            <div className="flex gap-2">
              <Button size="sm" variant="primary" onClick={saveOwn} disabled={!own.trim() || own.trim() === saved}>
                Save my wording
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setWriting(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" onClick={startWriting}>
              {saved ? "Edit my wording" : "Write my own"}
            </Button>
            {chosen && (
              <Button size="sm" variant="ghost" onClick={clear}>
                Clear stance
              </Button>
            )}
            {stance.status !== "archived" && (
              <Button size="sm" variant="ghost" icon={<Archive className="size-4" />} onClick={() => act({ type: "stance.delete", stance_id: stance.id })}>
                Archive
              </Button>
            )}
            {bg && (
              <a href={bg} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-[12.5px] text-accent hover:underline">
                Background reading <ExternalLink className="size-3.5" />
              </a>
            )}
          </div>
        )}
      </div>
      {stance.updated_at && <p className="mt-2 text-[12px] text-faint">Updated {formatDate(stance.updated_at, tz)}</p>}
    </article>
  );
}

export function Stances() {
  const view = useDesk((s) => s.view);
  const act = useDesk((s) => s.act);
  const [tier, setTier] = useState<Tier>("bihar");
  const [adding, setAdding] = useState(false);
  const [issue, setIssue] = useState("");
  const [newTier, setNewTier] = useState<Exclude<Tier, "archived">>("india");
  const [text, setText] = useState("");
  const stances = view?.stances ?? [];
  const byTier = useMemo(() => {
    const out: Record<Tier, Stance[]> = { world: [], india: [], bihar: [], other: [], archived: [] };
    for (const s of stances) (s.status === "archived" ? out.archived : out[(s.tier as Tier) ?? "other"] ?? out.other).push(s);
    return out;
  }, [stances]);
  const missing = stances.filter((s) => s.status !== "archived" && !s.chosen).length;
  const add = () => {
    if (!issue.trim()) return;
    act(
      { type: "stance.upsert", stance_id: newId("stn"), issue: issue.trim(), tier: newTier, ...(text.trim() ? { custom_text: text.trim() } : {}) },
      { toast: "Issue added." },
    );
    setAdding(false);
    setIssue("");
    setText("");
    setTier(newTier);
  };
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Stances</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Opinion posts on public issues are drafted only from what you record here (or say in an interview). The system lays out positions but never
            picks one for you. {missing > 0 && <b className="text-text">{missing} issue{missing === 1 ? "" : "s"} still without a stance.</b>}
          </p>
        </div>
        <div className="flex gap-2">
          <Button icon={<Sparkles className="size-4" />} onClick={() => act({ type: "stance.propose", count: 3 }, { toast: "Asked the system to propose new issues from recent coverage." })}>
            Propose issues
          </Button>
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
            Add issue
          </Button>
        </div>
      </header>
      <Tabs label="Tier" value={tier} onChange={setTier} items={TIERS.map((t) => ({ ...t, count: byTier[t.value].length }))} />
      {byTier[tier].length === 0 ? (
        <Empty title="Nothing here yet">Add an issue, or ask the system to propose some from recent coverage.</Empty>
      ) : (
        <div className="space-y-3">
          {byTier[tier].map((s) => (
            <StanceCard key={s.id} stance={s} />
          ))}
        </div>
      )}
      <Dialog
        open={adding}
        onClose={() => setAdding(false)}
        title="Add an issue"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAdding(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={add} disabled={!issue.trim()}>
              Add
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Issue" htmlFor="st-issue">
            <Input id="st-issue" value={issue} onChange={(e) => setIssue(e.target.value)} placeholder="For example: Patna Metro phase 2 priorities" />
          </Field>
          <Field label="Tier" htmlFor="st-tier">
            <Select id="st-tier" value={newTier} onChange={(e) => setNewTier(e.target.value as Exclude<Tier, "archived">)}>
              {TIERS.filter((t) => t.value !== "archived").map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Your stance (optional)" htmlFor="st-text">
            <Textarea id="st-text" value={text} onChange={(e) => setText(e.target.value)} minRows={2} />
          </Field>
        </div>
      </Dialog>
    </div>
  );
}
