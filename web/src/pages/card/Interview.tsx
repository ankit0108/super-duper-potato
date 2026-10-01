import { useEffect, useState } from "react";
import { Mic, MicOff, Sparkle } from "lucide-react";
import type { Card } from "@/types";
import { useDictation } from "@/lib/dictation";
import { readJSON, remove, writeJSON } from "@/lib/storage";
import { useDesk } from "@/state/store";
import { Button } from "@/components/ui/Button";
import { Checkbox, Field, Input, Textarea } from "@/components/ui/Field";

function AnswerField({ id, question, why, value, onChange }: { id: string; question: string; why?: string | null; value: string; onChange: (v: string) => void }) {
  const dictation = useDictation((t) => onChange(value ? `${value.trimEnd()} ${t}` : t));
  return (
    <Field label={question} htmlFor={id} hint={why || undefined} error={dictation.error ?? undefined}>
      <div className="relative">
        <Textarea id={id} value={value} onChange={(e) => onChange(e.target.value)} minRows={3} placeholder="Optional. A sentence or two is enough. Type or dictate." className="pr-12" />
        {dictation.supported && (
          <button
            type="button"
            onClick={dictation.listening ? dictation.stop : dictation.start}
            aria-pressed={dictation.listening}
            aria-label={dictation.listening ? "Stop dictation" : "Dictate an answer"}
            className={`absolute top-2 right-2 rounded-lg p-2 ${dictation.listening ? "animate-pulse bg-bad-soft text-bad" : "text-muted hover:bg-surface-2 hover:text-text"}`}
          >
            {dictation.listening ? <MicOff className="size-4" /> : <Mic className="size-4" />}
          </button>
        )}
      </div>
    </Field>
  );
}

/**
 * The card's questions. They're optional: a card usually arrives drafted from recent sources, and answering
 * redrafts it from his answers plus those sources. Without a draft yet, it can be drafted from sources only.
 */
export function Interview({ card }: { card: Card }) {
  const act = useDesk((s) => s.act);
  const key = `pbs.answers.${card.id}`;
  const questions = card.questions ?? [];
  const existing = Object.fromEntries((card.answers ?? []).map((a) => [a.question_id, a.answer]));
  const [answers, setAnswers] = useState<Record<string, string>>(() => ({ ...existing, ...readJSON<Record<string, string>>(key, {}) }));
  const [reusable, setReusable] = useState(true);
  const opinion = card.affairs_type === "opinion" || questions.some((q) => q.kind === "stance");
  const stanceQ = questions.find((q) => q.kind === "stance") ?? questions[0];
  const [saveStance, setSaveStance] = useState(opinion);
  const [issue, setIssue] = useState(card.title);
  const [stance, setStance] = useState<string | null>(null); // null: follows the stance question's answer
  useEffect(() => {
    writeJSON(key, answers);
  }, [answers, key]);
  const filled = questions.filter((q) => (answers[q.id] ?? "").trim());
  const stanceText = (stance ?? (stanceQ ? answers[stanceQ.id] ?? "" : "")).trim();
  const hasDraft = !!card.draft;
  const busy = !!card.work;

  const submit = () => {
    act(
      {
        type: "card.answers",
        card_id: card.id,
        answers: filled.map((q) => ({ question_id: q.id, answer: answers[q.id].trim() })),
        reusable,
        ...(opinion && saveStance && stanceText ? { save_as_stance: { stance_id: card.issue_key ?? null, issue: issue.trim() || card.title, text: stanceText.slice(0, 1000) } } : {}),
      },
      { toast: "Thanks. The new draft arrives within 1–3 minutes, built from your answers plus the sources." },
    );
    remove(key);
  };
  const draftFromSources = () => act({ type: "card.draft_now", card_id: card.id }, { toast: "Drafting it from recent sources. Takes 1–3 minutes." });

  if (!questions.length) return <p className="text-sm text-muted">No questions on this card yet. They arrive with the next run.</p>;
  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-border bg-surface-2 p-3.5 text-[13.5px]">
        {hasDraft ? (
          <>
            <b>Optional.</b> The draft is written from recent sources. Answer any of these, or none: your answers let the drafter add your own experience or view, using the
            sources for the facts.
          </>
        ) : (
          <>
            <b>Optional.</b> Answer any of these for a post in your own words, or draft it from recent sources without answering.
          </>
        )}{" "}
        Never name your employer, clients or colleagues.
      </div>
      {questions.map((q) => (
        <AnswerField key={q.id} id={`ans-${q.id}`} question={q.q} why={q.why} value={answers[q.id] ?? ""} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />
      ))}
      <Checkbox checked={reusable} onChange={setReusable} label="The drafter may reuse these answers in future posts on this pillar" description="Quoted as you said them, never stretched." />
      {opinion && (
        <div className="space-y-3 rounded-2xl border border-border p-3.5">
          <Checkbox checked={saveStance} onChange={setSaveStance} label="Save my view as my stance on the issue" description="Future opinion drafts on this issue use it. You can change it on the Stances page." />
          {saveStance && (
            <>
              <Field label="Issue" htmlFor="stance-issue">
                <Input id="stance-issue" value={issue} onChange={(e) => setIssue(e.target.value)} />
              </Field>
              <Field label="My stance, as it will be saved" htmlFor="stance-text" hint="Starts as your answer to the stance question. Edit it to say exactly what you think.">
                <Textarea id="stance-text" value={stance ?? (stanceQ ? answers[stanceQ.id] ?? "" : "")} onChange={(e) => setStance(e.target.value)} minRows={2} maxLength={1000} />
              </Field>
            </>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-[13px] text-muted">
          {filled.length}/{questions.length} answered
        </span>
        <div className="flex flex-wrap gap-2">
          {!hasDraft && (
            <Button variant="secondary" icon={<Sparkle className="size-4" />} onClick={draftFromSources} disabled={busy}>
              Draft from sources only
            </Button>
          )}
          <Button variant="primary" onClick={submit} disabled={!filled.length || busy}>
            Draft from my answers + sources
          </Button>
        </div>
      </div>
    </div>
  );
}
