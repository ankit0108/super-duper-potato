import { useState } from "react";
import { Hash, Plus, X } from "lucide-react";
import type { Platform } from "@/types";
import { normalizeTag, sameTag } from "@/lib/hashtags";
import { Button, cx } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";

/**
 * The suggested hashtags as chips: tap to drop or bring one back, or add his own. The chosen ones are added at
 * the end when he copies, opens the app or marks the post as posted. What he keeps teaches the drafter.
 */
export function HashtagsBar({ platform, suggested, chosen, onChange }: { platform: Platform; suggested: string[]; chosen: string[]; onChange: (tags: string[]) => void }) {
  const [adding, setAdding] = useState("");
  const all = [...suggested, ...chosen.filter((t) => !suggested.some((s) => sameTag(s, t)))];
  const isOn = (t: string) => chosen.some((c) => sameTag(c, t));
  const toggle = (t: string) => onChange(isOn(t) ? chosen.filter((c) => !sameTag(c, t)) : [...chosen, t]);
  const add = () => {
    const tag = normalizeTag(adding);
    if (tag && !isOn(tag)) onChange([...chosen, tag]);
    setAdding("");
  };
  const advice = platform === "linkedin" ? "LinkedIn: 3 to 5 help the right people find it." : "X: 1 or 2 at most; none is fine.";
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[13px] font-semibold">Hashtags</h3>
        <span className="text-xs text-muted">{advice}</span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Hashtags">
        {all.map((t) => (
          <button
            key={t}
            type="button"
            aria-pressed={isOn(t)}
            onClick={() => toggle(t)}
            title={isOn(t) ? "Added at the end when you copy or post. Tap to drop it." : "Tap to add it back"}
            className={cx(
              "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[13px] transition-colors",
              isOn(t) ? "border-accent bg-accent-soft text-accent" : "border-border text-muted line-through decoration-1 hover:text-text",
            )}
          >
            {t}
            {isOn(t) && <X className="size-3" aria-hidden />}
          </button>
        ))}
        <form
          className="inline-flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            add();
          }}
        >
          <Input aria-label="Add a hashtag" value={adding} onChange={(e) => setAdding(e.target.value)} placeholder="#YourTag" className="h-8 w-32 text-[13px]" />
          <Button size="sm" variant="ghost" type="submit" icon={<Plus className="size-4" />} disabled={!normalizeTag(adding)} aria-label="Add hashtag">
            Add
          </Button>
        </form>
      </div>
      <p className="flex items-center gap-1 text-xs text-muted">
        <Hash className="size-3" aria-hidden /> {chosen.length ? `Added at the end when you copy, open ${platform === "x" ? "X" : "LinkedIn"} or mark it posted.` : "None: the post goes out without hashtags."}
      </p>
    </div>
  );
}
