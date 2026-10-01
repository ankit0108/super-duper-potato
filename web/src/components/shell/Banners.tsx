import { useState } from "react";
import { useDesk } from "@/state/store";
import { useNow } from "@/state/hooks";
import { relative } from "@/lib/time";
import { navigate } from "@/lib/router";
import { Button } from "../ui/Button";
import { Banner } from "../ui/Feedback";

const STALE_HOURS = 30;

/** Everything that needs Ankit's attention about the system itself, shown above every page. */
export function Banners() {
  const view = useDesk((s) => s.view);
  const loadError = useDesk((s) => s.loadError);
  const mode = useDesk((s) => s.connection?.mode);
  const workflowState = useDesk((s) => s.workflowState);
  const enable = useDesk((s) => s.enableWorkflow);
  const dispatch = useDesk((s) => s.dispatchNow);
  const run = useDesk((s) => s.run);
  const update = useDesk((s) => s.update);
  const now = useNow(60_000);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const dismiss = (k: string) => setDismissed(new Set([...dismissed, k]));

  const generated = view?.meta?.generated_at ? new Date(view.meta.generated_at) : null;
  const stale = mode === "github" && generated && (now.getTime() - generated.getTime()) / 3600_000 > STALE_HOURS;
  const disabled = workflowState && workflowState !== "active" && workflowState !== "unknown";
  const serverWarnings = (view?.warnings ?? []).filter((w) => w.level !== "info" && !dismissed.has(w.code));

  const items = [];
  if (update) {
    items.push(
      <Banner
        key="update"
        tone="info"
        action={
          <Button size="sm" variant="secondary" onClick={() => window.location.reload()}>
            Reload
          </Button>
        }
      >
        The desk was updated. Reload to get the new version (your edits are kept).
      </Banner>,
    );
  }
  if (mode === "demo" && !dismissed.has("demo")) {
    items.push(
      <Banner
        key="demo"
        tone="info"
        onDismiss={() => dismiss("demo")}
        action={
          <Button size="sm" variant="soft" onClick={() => navigate("/connect")}>
            Connect
          </Button>
        }
      >
        Demo mode: sample data, and your changes stay in this browser. Connect your data repo to use the real desk.
      </Banner>,
    );
  }
  if (loadError) items.push(<Banner key="load" tone={mode === "github" && loadError.startsWith("Offline") ? "warn" : "bad"}>{loadError}</Banner>);
  if (disabled) {
    items.push(
      <Banner
        key="wf"
        tone="bad"
        action={
          <Button size="sm" variant="secondary" onClick={() => void enable()}>
            Re-enable
          </Button>
        }
      >
        GitHub has disabled the pipeline's schedule ({workflowState?.replace(/_/g, " ")}). No drafts will arrive until it is re-enabled.
      </Banner>,
    );
  }
  if (stale && !disabled) {
    items.push(
      <Banner
        key="stale"
        tone="warn"
        action={
          <Button size="sm" variant="secondary" loading={run.state === "queued" || run.state === "running"} onClick={() => void dispatch()}>
            Run now
          </Button>
        }
      >
        The pipeline last ran {relative(generated, now)}. Scheduled runs may be failing: check System.
      </Banner>,
    );
  }
  for (const w of serverWarnings.slice(0, 3)) {
    items.push(
      <Banner key={w.code} tone={w.level === "error" ? "bad" : "warn"} onDismiss={() => dismiss(w.code)}>
        {w.message}
      </Banner>,
    );
  }
  if (!items.length) return null;
  return <div className="mb-4 space-y-2">{items}</div>;
}
