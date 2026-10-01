import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import type { Platform } from "@/types";
import { useDesk } from "@/state/store";
import { Button } from "./ui/Button";
import { Dialog } from "./ui/Dialog";
import { Checkbox } from "./ui/Field";
import { Segmented } from "./ui/Tabs";

type Count = "usual" | "1" | "2" | "3" | "5";

/**
 * "Get fresh posts": a new set now, on top of today's picks. The pipeline looks for new stories (unless he says
 * not to), ranks them against what he has already seen today and drafts the set, as the morning run does.
 */
export function FreshPostsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const act = useDesk((s) => s.act);
  const view = useDesk((s) => s.view);
  const prefs = useDesk((s) => s.prefs);
  const settings = view?.settings as Record<string, any> | undefined;
  const usual: Record<Platform, number> = { linkedin: settings?.platforms?.linkedin?.slots ?? 3, x: settings?.platforms?.x?.slots ?? 6 };
  const [which, setWhich] = useState<"both" | Platform>("both");
  const [count, setCount] = useState<Count>("usual");
  const [find, setFind] = useState(true);
  useEffect(() => {
    if (open) setWhich(prefs.platform === "all" ? "both" : prefs.platform);
  }, [open, prefs.platform]);

  const platforms: Platform[] = which === "both" ? ["linkedin", "x"] : [which];
  const total = platforms.reduce((n, p) => n + (count === "usual" ? usual[p] : Number(count)), 0);
  const plural = (n: number) => `${n} fresh post${n === 1 ? "" : "s"}`;
  const go = () => {
    act(
      {
        type: "run.request",
        tasks: ["morning"],
        force: true,
        platforms: which === "both" ? null : platforms,
        per_platform: count === "usual" ? null : Number(count),
        find_sources: find,
      },
      { toast: `Getting ${plural(total)}. They land on top of Today's picks, usually within 2–4 minutes.` },
    );
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Get fresh posts"
      description="A new set now: new stories, ranked against what you've already seen today, then drafted."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" icon={<Sparkles className="size-4" />} onClick={go}>
            Get {plural(total)}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <p className="mb-1.5 text-sm font-medium">Platforms</p>
          <Segmented
            label="Platforms"
            value={which}
            onChange={setWhich}
            items={[
              { value: "both", label: "Both" },
              { value: "linkedin", label: "LinkedIn" },
              { value: "x", label: "X" },
            ]}
          />
        </div>
        <div>
          <p className="mb-1.5 text-sm font-medium">Cards per platform</p>
          <Segmented
            label="Cards per platform"
            value={count}
            onChange={setCount}
            items={[
              { value: "usual", label: which === "both" ? `Usual (${usual.linkedin} + ${usual.x})` : `Usual (${usual[which]})` },
              { value: "1", label: "1" },
              { value: "2", label: "2" },
              { value: "3", label: "3" },
              { value: "5", label: "5" },
            ]}
          />
        </div>
        <Checkbox
          checked={find}
          onChange={setFind}
          label="Look for new stories first"
          description="Off: picks from stories found in the last few days, which is quicker."
        />
      </div>
    </Dialog>
  );
}
