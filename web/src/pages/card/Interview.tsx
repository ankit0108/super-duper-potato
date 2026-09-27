import { useEffect, useState } from "react";
import { Mic, MicOff } from "lucide-react";
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
        <Textarea id={id} value={value} onChange={(e) => onChange(e.target.value)} minRows={3} placeholder="A sentence or two is enough. Type or dictate." className="pr-12" />
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

export function Interview({ card }: { card: Card }) {
  const act = useDesk((s) => s.act);
  const key = `pbs.answers.${card.id}`;
  const questions = card.questions ?? [];
  const existing = Object.fromEntries((card.answers ?? []).map((a) => [a.question_id, a.answer]));
  const [answers, setAnswers] = useState<Record<string, string>>(() => ({ ...existing, ...readJSON<Record<string, string>>(key, {}) }));
  const [reusable, setReusable] = useState(true);
  const opinion = card.affairs_type === "opinion" || questions.some((q) => q.kind === "stance");
  const [saveStance, setSaveStance] = useState(opinion);
  const [issue, setIssue] = useState(card.title);
  useEffect(() => {
    writeJSON(key, answers);
  }, [answers, key]);
  const filled = questions.filter((q) => (answers[q.id] ?? "").trim());
  const submit = () => {
    act(
      {
        type: "card.answers",
        card_id: card.id,
        answers: filled.map((q) => ({ question_id: q.id, answer: answers[q.id].trim() })),
        reusable,
        ...(opinion && saveStance
          ? { save_as_stance: { stance_id: card.issue_key ?? null, issue: issue.trim() || card.title, text: filled.map((q) => answers[q.id].trim()).join(" ").slice(0, 1000) } }
          : {}),
      },
      { toast: "Thanks. The draft arrives in about two minutes, written only from your answers." },
    );
    remove(key);
  };
  if (!questions.length) return <p className="text-sm text-muted">No questions on this card yet. They arrive with the next run.</p>;
  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-warn/30 bg-warn-soft p-3.5 text-[13.5px]">
        <b className="text-warn">Your input needed.</b> This post has to come from your own experience or view, so the draft is written only from what you say here. Never
        name your employer, clients or colleagues.
      </div>
      {questions.map((q) => (
        <AnswerField key={q.id} id={`ans-${q.id}`} question={q.q} why={q.why} value={answers[q.id] ?? ""} onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))} />
      ))}
      <Checkbox checked={reusable} onChange={setReusable} label="The drafter may reuse these answers in future posts on this pillar" description="Quoted as you said them, never stretched." />
      {opinion && (
        <div className="space-y-3 rounded-2xl border border-border p-3.5">
          <Checkbox checked={saveStance} onChange={setSaveStance} label="Save this as my stance on the issue" description="Future opinion drafts on this issue use it. You can change it on the Stances page." />
          {saveStance && (
            <Field label="Issue" htmlFor="stance-issue">
              <Input id="stance-issue" value={issue} onChange={(e) => setIssue(e.target.value)} />
            </Field>
          )}
        </div>
      )}
      <div className="flex items-center justify-between gap-3">
        <span className="text-[13px] text-muted">
          {filled.length}/{questions.length} answered
        </span>
        <Button variant="primary" onClick={submit} disabled={!filled.length}>
          Draft from my answers
        </Button>
      </div>
    </div>
  );
}
