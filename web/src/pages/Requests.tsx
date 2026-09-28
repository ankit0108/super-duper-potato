import { useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import type { RequestRow } from "@/types";
import { FORMAT_LABEL, draftText } from "@/lib/format";
import { newId } from "@/lib/storage";
import { opening } from "@/lib/text";
import { Link } from "@/lib/router";
import { formatDateTime } from "@/lib/time";
import { useDesk } from "@/state/store";
import { useTz } from "@/state/hooks";
import { Badge, PlatformMark, type Tone } from "@/components/ui/Badge";
import { Button, cx } from "@/components/ui/Button";
import { Empty, Panel } from "@/components/ui/Feedback";
import { Field, Stepper, Textarea } from "@/components/ui/Field";

const STATUS: Record<RequestRow["status"] & string, { tone: Tone; label: string }> = {
  queued: { tone: "info", label: "Queued" },
  running: { tone: "accent", label: "Searching and drafting" },
  done: { tone: "ok", label: "Done" },
  partial: { tone: "warn", label: "Partly drafted" },
  failed: { tone: "bad", label: "Failed" },
  cancelled: { tone: "neutral", label: "Cancelled" },
};

const PRESETS = [
  { label: "LinkedIn", li: 2, x: 0 },
  { label: "X", li: 0, x: 3 },
  { label: "Both", li: 2, x: 3 },
];

type SearchInfo = { interpretation?: string; queries?: string[]; exclude?: string[]; recency_days?: number; results?: number; kept?: number; checked?: boolean };

/** What the search understood, so a wrong reading is visible (and fixable with the notes field). */
function SearchSummary({ search }: { search: SearchInfo }) {
  return (
    <div className="mt-2 rounded-xl bg-surface-2 px-3 py-2 text-[12.5px] text-muted">
      <p>
        <span className="font-medium text-text">Understood as:</span> {search.interpretation}
      </p>
      <p className="mt-0.5">
        Searched {search.queries?.length ? search.queries.map((q) => `“${q}”`).join(", ") : "the topic"}
        {search.exclude?.length ? `, leaving out ${search.exclude.join(", ")}` : ""}
        {search.recency_days ? `, last ${search.recency_days} days` : ""}
        {search.results != null ? ` · ${search.kept ?? 0} of ${search.results} results kept${search.checked ? " after a relevance check" : ""}` : ""}
      </p>
    </div>
  );
}

export function Requests() {
  const view = useDesk((s) => s.view);
  const act = useDesk((s) => s.act);
  const tz = useTz();
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState("");
  const [li, setLi] = useState(2);
  const [x, setX] = useState(3);
  const requests = view?.requests ?? [];
  const cards = new Map((view?.cards ?? []).map((c) => [c.id, c]));

  const submit = () => {
    const q = query.trim();
    if (q.length < 2 || li + x === 0) return;
    act(
      { type: "request.create", request_id: newId("req"), query: q, platforms: { linkedin: li, x }, notes: notes.trim() || null },
      { toast: "On it. Searching beyond the daily sources and drafting; results in a few minutes." },
    );
    setQuery("");
    setNotes("");
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Requests</h1>
        <p className="mt-1 text-sm text-muted">
          Any topic, any time. The pipeline first works out what you mean from your profile and pillars (so “AI automation” means automating business processes, not factory robots), then
          searches recent Google News, Hacker News, arXiv and Reddit, keeps what's relevant and returns full drafts.
        </p>
      </header>
      <Panel title="New request">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Field label="Topic" htmlFor="rq-q" hint='For example "Bihar semiconductor packaging plans" or "evals for agentic RPA".'>
            <Textarea id="rq-q" value={query} onChange={(e) => setQuery(e.target.value)} minRows={2} placeholder="What should the drafts be about?" />
          </Field>
          <Field label="Angle or notes (optional)" htmlFor="rq-n" hint="What you mean or want, for example “automation tools for manual business processes, not robotics”. The search and the drafter both use it.">
            <Textarea id="rq-n" value={notes} onChange={(e) => setNotes(e.target.value)} minRows={2} />
          </Field>
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Platforms">
            <span className="mr-1 text-[13px] font-medium">Drafts for</span>
            {PRESETS.map((pr) => (
              <button
                key={pr.label}
                type="button"
                aria-pressed={li === pr.li && x === pr.x}
                onClick={() => {
                  setLi(pr.li);
                  setX(pr.x);
                }}
                className={cx(
                  "rounded-full border px-3 py-1 text-[13px] transition-colors",
                  li === pr.li && x === pr.x ? "border-accent bg-accent-soft text-accent" : "border-border text-muted hover:text-text",
                )}
              >
                {pr.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-end gap-6">
            <div className="space-y-1.5">
              <span className="flex items-center gap-1.5 text-[13px] font-medium">
                <PlatformMark platform="linkedin" className="size-4 text-[9px]" /> LinkedIn drafts
              </span>
              <Stepper label="LinkedIn drafts" value={li} onChange={setLi} max={5} />
            </div>
            <div className="space-y-1.5">
              <span className="flex items-center gap-1.5 text-[13px] font-medium">
                <PlatformMark platform="x" className="size-4 text-[9px]" /> X drafts
              </span>
              <Stepper label="X drafts" value={x} onChange={setX} max={5} />
            </div>
            <Button type="submit" variant="primary" icon={<Search className="size-4" />} disabled={query.trim().length < 2 || li + x === 0} className="ml-auto">
              Search and draft
            </Button>
          </div>
        </form>
      </Panel>

      <section className="space-y-3">
        <h2 className="text-[15px] font-semibold">Recent requests</h2>
        {requests.length === 0 ? (
          <Empty title="No requests yet">Requests are how you point the system at interests its daily scouts miss. They also nudge what it scouts for.</Empty>
        ) : (
          <ul className="space-y-2.5">
            {requests.map((r) => {
              const st = STATUS[r.status ?? "queued"];
              const results = (r.card_ids ?? []).map((id) => cards.get(id)).filter(Boolean);
              return (
                <li key={r.id} className="rounded-2xl border border-border bg-surface p-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium">{r.query}</p>
                      <p className="mt-0.5 text-[12.5px] text-muted">
                        {formatDateTime(r.created_at, tz)} · {Object.entries(r.platforms ?? {})
                          .filter(([, n]) => n)
                          .map(([p, n]) => `${n} ${p === "x" ? "X" : "LinkedIn"}`)
                          .join(", ")}
                        {r.notes ? ` · “${r.notes}”` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={st.tone} icon={r.status === "running" || r.status === "queued" ? <Loader2 className="size-3 animate-spin" /> : undefined}>
                        {st.label}
                      </Badge>
                      {(r.status === "queued" || r.status === "failed") && (
                        <Button size="sm" variant="ghost" icon={<X className="size-4" />} onClick={() => act({ type: "request.cancel", request_id: r.id })}>
                          Cancel
                        </Button>
                      )}
                    </div>
                  </div>
                  {r.error && <p className="mt-2 text-[13px] text-bad">{r.error}</p>}
                  {!!(r.search as SearchInfo | null | undefined)?.interpretation && <SearchSummary search={r.search as SearchInfo} />}
                  {results.length > 0 && (
                    <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                      {results.map((c) => (
                        <li key={c!.id}>
                          <Link to={`/card/${c!.id}`} className="flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-[13px] hover:bg-surface-2">
                            <PlatformMark platform={c!.platform} className="size-4 text-[9px]" />
                            <span className="min-w-0 flex-1 truncate">{opening(draftText(c!)) || c!.angle || c!.title}</span>
                            <span className="shrink-0 text-[12px] text-faint">{FORMAT_LABEL[c!.format]}</span>
                            <Badge tone={c!.status === "posted" ? "ok" : "neutral"}>{c!.status === "posted" ? "Posted" : c!.draft_state === "brief" ? "Brief" : "Draft"}</Badge>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
