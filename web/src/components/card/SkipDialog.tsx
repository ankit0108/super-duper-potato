import { useEffect, useState } from "react";
import type { SkipReason } from "@/types";
import { MENU_SKIP_REASONS, SKIP_REASONS } from "@/lib/format";
import { useDesk } from "@/state/store";
import { Button, cx } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Field, Textarea } from "../ui/Field";

/**
 * "Why skip it?" for one card: "Other" can't be sent without a reason, and a one-tap skip can add one later.
 * Mounted once in the app shell, so the toast's "Add why" still works after the card has left the screen.
 */
export function SkipDialogHost() {
  const prompt = useDesk((s) => s.skipPrompt);
  const close = useDesk((s) => s.closeSkipPrompt);
  const act = useDesk((s) => s.act);
  const card = useDesk((s) => (prompt ? s.view?.cards?.find((c) => c.id === prompt.cardId) : undefined));
  const [reason, setReason] = useState<SkipReason>("other");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!prompt) return;
    setReason(prompt.reason);
    setNote(card?.skip?.note ?? "");
    // Only when the dialog opens; later updates to the card must not wipe what's being typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prompt]);

  const info = SKIP_REASONS.find((r) => r.value === reason);
  const needsNote = !!info?.needsNote;
  const ready = !needsNote || note.trim().length > 0;
  const confirm = () => {
    if (!prompt || !ready) return;
    act({ type: "card.skip", card_id: prompt.cardId, reason, note: note.trim() || null }, { toast: `Skipped. ${info?.learns ?? ""}`.trim() });
    close();
  };

  return (
    <Dialog
      open={!!prompt}
      onClose={close}
      title="Why skip it?"
      description={card?.title}
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button variant="primary" onClick={confirm} disabled={!ready}>
            Skip with this reason
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div role="radiogroup" aria-label="Reason" className="flex flex-wrap gap-1.5">
          {MENU_SKIP_REASONS.map((r) => (
            <button
              key={r.value}
              type="button"
              role="radio"
              aria-checked={reason === r.value}
              onClick={() => setReason(r.value)}
              className={cx(
                "rounded-full border px-3 py-1 text-[13px] transition-colors",
                reason === r.value ? "border-accent bg-accent-soft text-accent" : "border-border text-muted hover:text-text",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
        <Field
          label={needsNote ? "What's wrong with this suggestion?" : "Anything to add? (optional)"}
          htmlFor="skip-note"
          hint="For example: “industrial automation, not my focus: I mean automating business processes”."
        >
          <Textarea id="skip-note" value={note} onChange={(e) => setNote(e.target.value)} minRows={3} maxLength={1000} autoFocus />
        </Field>
        {info && <p className="text-[13px] text-muted">{info.learns}</p>}
      </div>
    </Dialog>
  );
}
