import { useState, type ReactNode } from "react";
import { CheckCircle2, CircleSlash, Loader2, OctagonAlert, TriangleAlert } from "lucide-react";
import type { Run } from "@/types";
import { formatDateTime, relative } from "@/lib/time";
import { useDesk } from "@/state/store";
import { useNow, useTz } from "@/state/hooks";
import { Badge, type Tone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Empty, Panel } from "@/components/ui/Feedback";

const RUN_TONE: Record<string, Tone> = { ok: "ok", partial: "warn", failed: "bad", running: "info" };

function RunRow({ run, now }: { run: Run; now: Date }) {
  const [open, setOpen] = useState(false);
  const secs = run.ended_at ? Math.round((new Date(run.ended_at).getTime() - new Date(run.started_at).getTime()) / 1000) : null;
  const llm = run.llm as { calls?: number; by_provider?: Record<string, number>; fallbacks?: number } | undefined;
  return (
    <li className="px-4 py-2.5">
      <button type="button" className="flex w-full flex-wrap items-center gap-2 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Badge tone={RUN_TONE[run.status ?? "ok"]}>{run.status}</Badge>
        <span className="text-[13.5px] font-medium">{run.trigger === "schedule" ? "Scheduled" : run.trigger === "workflow_dispatch" ? "From the desk" : run.trigger}</span>
        <span className="text-[12.5px] text-muted">{relative(run.started_at, now)}</span>
        {secs != null && <span className="text-[12.5px] text-muted">· {secs}s</span>}
        {llm?.calls != null && <span className="text-[12.5px] text-muted">· {llm.calls} model calls</span>}
        {run.degraded && <Badge tone="warn">{run.degraded.replace(/_/g, " ")}</Badge>}
        {(run.errors ?? []).length > 0 && <Badge tone="bad">{run.errors!.length} error(s)</Badge>}
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-[12.5px]">
          <div className="flex flex-wrap gap-1.5">
            {(run.steps ?? []).map((s, i) => (
              <Badge key={i} tone={s.status === "ok" ? "neutral" : "bad"}>
                {String(s.name)} {typeof s.secs === "number" ? `${s.secs}s` : ""}
              </Badge>
            ))}
          </div>
          {llm?.by_provider && (
            <p className="text-muted">
              Providers: {Object.entries(llm.by_provider).map(([k, v]) => `${k} ${v}`).join(", ") || "none"}
              {llm.fallbacks ? ` · ${llm.fallbacks} fallback(s)` : ""}
            </p>
          )}
          {(run.notes ?? []).map((n, i) => (
            <p key={i}>• {n}</p>
          ))}
          {(run.errors ?? []).map((e, i) => (
            <p key={i} className="text-bad">
              {e.type} in {e.where}
              {e.message ? `: ${e.message}` : ""}
            </p>
          ))}
        </div>
      )}
    </li>
  );
}

function Check({ status }: { status: string }) {
  const icons: Record<string, ReactNode> = {
    ok: <CheckCircle2 className="size-4 text-ok" aria-label="OK" />,
    warn: <TriangleAlert className="size-4 text-warn" aria-label="Warning" />,
    fail: <OctagonAlert className="size-4 text-bad" aria-label="Failed" />,
    skip: <CircleSlash className="size-4 text-faint" aria-label="Skipped" />,
  };
  return <>{icons[status] ?? icons.skip}</>;
}

export function System() {
  const view = useDesk((s) => s.view);
  const act = useDesk((s) => s.act);
  const run = useDesk((s) => s.run);
  const workflowState = useDesk((s) => s.workflowState);
  const enable = useDesk((s) => s.enableWorkflow);
  const outbox = useDesk((s) => s.outbox);
  const retry = useDesk((s) => s.retryFailed);
  const conn = useDesk((s) => s.connection);
  const rate = useDesk((s) => s.rateRemaining);
  const tz = useTz();
  const now = useNow(30_000);
  const busy = run.state === "queued" || run.state === "running";
  const request = (tasks: Array<"morning" | "weekly_batch" | "reflection" | "doctor" | "scout">, force: boolean, toast: string) =>
    act({ type: "run.request", tasks, force }, { toast });
  const today = view?.delivery?.local_date;
  const deliveredToday = today && view?.meta?.generated_at && today === new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(now);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">System</h1>
        <p className="mt-1 text-sm text-muted">Runs, free-tier usage and health. Every run does whatever is due, so a missed schedule catches up on the next one.</p>
      </header>

      <Panel title="Run now" description="Starts the pipeline on GitHub Actions. Results appear here and on the board in a few minutes.">
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" loading={busy} onClick={() => request([], false, "Sync started.")}>
            Sync now
          </Button>
          <Button onClick={() => request(["morning"], true, deliveredToday ? "Getting another set of cards." : "Delivering the morning set.")} disabled={busy}>
            {deliveredToday ? "Get another set" : "Deliver the morning set"}
          </Button>
          <Button onClick={() => request(["scout"], false, "Refreshing sources.")} disabled={busy}>
            Refresh sources
          </Button>
          <Button onClick={() => request(["weekly_batch"], true, "Preparing this week's evergreen and interview cards.")} disabled={busy}>
            Prepare weekly batch
          </Button>
          <Button onClick={() => request(["reflection"], false, "Running the weekly review.")} disabled={busy}>
            Run weekly review
          </Button>
          <Button onClick={() => request(["doctor"], false, "Running the doctor checks.")} disabled={busy}>
            Run doctor
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-muted">
          <span>
            Pipeline:{" "}
            {busy ? (
              <span className="inline-flex items-center gap-1 text-accent">
                <Loader2 className="size-3.5 animate-spin" /> {run.state === "queued" ? "starting" : "running"}
              </span>
            ) : run.state === "failed" ? (
              <span className="text-bad">last run failed</span>
            ) : (
              "idle"
            )}
            {run.url && (
              <>
                {" "}
                ·{" "}
                <a href={run.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  logs
                </a>
              </>
            )}
          </span>
          <span>Desk updated {relative(view?.meta?.generated_at, now)}</span>
          {view?.meta?.next_delivery_local && <span>Next delivery {formatDateTime(new Date(view.meta.next_delivery_local), tz)}</span>}
          {conn?.mode === "github" && (
            <span>
              Schedule: {workflowState ?? "checking…"}
              {workflowState && workflowState !== "active" && (
                <Button size="sm" variant="ghost" onClick={() => void enable()}>
                  Re-enable
                </Button>
              )}
            </span>
          )}
          {rate != null && <span>GitHub API: {rate} requests left this hour</span>}
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Free-tier usage today" description="Calls per provider (UTC day). When one runs out, the next in the chain takes over.">
          {(view?.quota ?? []).length === 0 ? (
            <p className="text-[13px] text-muted">No model calls yet today.</p>
          ) : (
            <ul className="space-y-2.5">
              {(view?.quota ?? []).map((q) => {
                const limit = q.daily_limit ?? 0;
                const ratio = limit ? Math.min(1, (q.requests ?? 0) / limit) : 0;
                return (
                  <li key={q.provider}>
                    <div className="mb-1 flex justify-between text-[13px]">
                      <span>{q.provider}</span>
                      <span className="text-muted tabular-nums">
                        {q.requests ?? 0}
                        {limit ? ` / ${limit}` : ""} {q.exhausted_at && <Badge tone="warn">quota reached</Badge>}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-accent-soft" role="img" aria-label={`${q.provider}: ${q.requests} of ${limit} calls`}>
                      <div className="h-full rounded-full" style={{ width: `${ratio * 100}%`, background: ratio > 0.85 || q.exhausted_at ? "var(--warn)" : "var(--accent)" }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
        <Panel title="Doctor" description={view?.doctor ? `Checked ${relative(view.doctor.created_at, now)}` : "Checks secrets, each model provider, Google Search grounding and every source."}>
          {view?.doctor ? (
            <ul className="space-y-1.5">
              {(view.doctor.checks ?? []).map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-[13px]">
                  <Check status={c.status} />
                  <span>
                    <b className="font-medium">{c.name}</b>
                    {c.detail ? <span className="text-muted"> · {c.detail}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-muted">Not run yet. Use Run doctor above.</p>
          )}
        </Panel>
      </div>

      <Panel title="Recent runs">
        {(view?.runs ?? []).length === 0 ? (
          <Empty title="No runs yet">The first run starts on the schedule, or with Sync now.</Empty>
        ) : (
          <ul className="-mx-4 -my-2 divide-y divide-border">
            {(view?.runs ?? []).map((r) => (
              <RunRow key={r.id} run={r} now={now} />
            ))}
          </ul>
        )}
      </Panel>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Your changes in flight" description="Saved on this device and in your data repo, waiting for the next run to apply them.">
          {outbox.length === 0 ? (
            <p className="text-[13px] text-muted">Nothing pending.</p>
          ) : (
            <>
              <ul className="space-y-1 text-[13px]">
                {outbox.slice(-12).map((i) => (
                  <li key={i.event.id} className="flex items-center justify-between gap-2">
                    <span className="truncate">{i.event.type}</span>
                    <Badge tone={i.state === "failed" ? "bad" : i.state === "sent" ? "neutral" : "info"}>{i.state === "sent" ? "waiting for a run" : i.state}</Badge>
                  </li>
                ))}
              </ul>
              {outbox.some((i) => i.state === "failed") && (
                <Button size="sm" className="mt-3" onClick={retry}>
                  Retry failed
                </Button>
              )}
            </>
          )}
        </Panel>
        <Panel title="Rejected changes" description="Events the pipeline couldn't apply, with the reason (last 14 days).">
          {(view?.rejected_events ?? []).length === 0 ? (
            <p className="text-[13px] text-muted">None.</p>
          ) : (
            <ul className="space-y-1.5 text-[13px]">
              {(view?.rejected_events ?? []).map((r) => (
                <li key={r.id}>
                  <b className="font-medium">{r.type}</b> <span className="text-muted">· {relative(r.at, now)}</span>
                  <div className="text-bad">{r.error}</div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
