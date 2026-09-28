import { useMemo, useState } from "react";
import { Check, CircleDashed, Plus, Trash2, X } from "lucide-react";
import type { DeskState, Platform, PlaybookRule, Proposal } from "@/types";
import { SKIP_REASONS, num, pct } from "@/lib/format";
import { formatDate, localDateKey } from "@/lib/time";
import { Link, useRoute, navigate } from "@/lib/router";
import { useDesk } from "@/state/store";
import { usePillarLabels, useTz } from "@/state/hooks";
import { Badge, PlatformMark, type Tone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Empty, Panel } from "@/components/ui/Feedback";
import { Field, Select, Textarea } from "@/components/ui/Field";
import { Tabs } from "@/components/ui/Tabs";
import { ChartCard, ColumnChart, DataTable, DaysGrid, LegendKey, LineChart, ShareBars, StatTile } from "@/components/charts/Charts";

type WeekRow = { week: string } & Record<Platform, Record<string, number | null>>;
type Stats = {
  weekly?: WeekRow[];
  daily?: Array<{ date: string; linkedin: number; x: number; delivered: boolean; delivered_local?: string | null }>;
  pillar_mix?: Record<Platform, Record<string, { label: string; weight: number; delivered: number; picked: number; posted: number }>>;
  followers?: Record<Platform, Array<{ date: string; followers: number }>>;
  streak?: Record<string, number>;
  gates?: Array<{ gate: number; name: string; target: string; value: string; met: boolean }>;
};

const COLORS: Record<Platform, string> = { linkedin: "var(--series-1)", x: "var(--series-2)" };
const NAMES: Record<Platform, string> = { linkedin: "LinkedIn", x: "X" };
const wk = (w: string) => w.replace(/^\d{4}-/, "");

function delta(now: number | null | undefined, prev: number | null | undefined, fmt: (n: number) => string, lowerIsBetter = false, versus = "last week") {
  if (now == null || prev == null) return { text: null, good: null };
  const d = now - prev;
  if (Math.abs(d) < 1e-9) return { text: `Same as ${versus}`, good: null };
  const good = lowerIsBetter ? d < 0 : d > 0;
  return { text: `${d > 0 ? "+" : "−"}${fmt(Math.abs(d))} vs ${versus}`, good };
}

const addDays = (date: string, n: number) => new Date(Date.parse(`${date}T00:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);

function Overview({ view }: { view: DeskState }) {
  const tz = useTz();
  const stats = (view.stats ?? {}) as Stats;
  const weekly = stats.weekly ?? [];
  const labels = weekly.map((w) => wk(w.week));
  const cur = weekly[weekly.length - 1];
  const val = (row: WeekRow | undefined, p: Platform, k: string) => (row?.[p]?.[k] as number | null | undefined) ?? null;
  const followers = stats.followers ?? { linkedin: [], x: [] };
  const lastF = (p: Platform) => followers[p]?.[followers[p].length - 1]?.followers ?? null;
  const fourWeeksAgo = (p: Platform) => {
    const rows = followers[p] ?? [];
    if (rows.length < 2) return null;
    const cutoff = new Date(Date.now() - 28 * 86400_000).toISOString().slice(0, 10);
    return [...rows].reverse().find((r) => r.date <= cutoff)?.followers ?? rows[0].followers;
  };
  const rank1 = weekly
    .slice(-4)
    .flatMap((w) => [w.linkedin?.rank1_rate, w.x?.rank1_rate])
    .filter((v): v is number => v != null);
  const days = stats.daily ?? [];
  const mix = stats.pillar_mix;
  // Week to date (Monday to today, in the desk's timezone), compared with the same days last week, so a
  // Monday morning isn't "−7 vs last week".
  const todayKey = localDateKey(new Date(), tz);
  const monday = addDays(todayKey, -((new Date(`${todayKey}T00:00:00Z`).getUTCDay() + 6) % 7));
  const postsBetween = (p: Platform, from: string, to: string) => days.filter((d) => d.date >= from && d.date <= to).reduce((n, d) => n + (d[p] ?? 0), 0);
  const latestEdit = (p: Platform) => {
    const rows = weekly.filter((w) => w[p]?.edit_ratio_median != null);
    return { last: rows[rows.length - 1], before: rows[rows.length - 2] };
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {(["linkedin", "x"] as const).map((p) => {
          const thisWeek = postsBetween(p, monday, todayKey);
          const sameTimeLastWeek = postsBetween(p, addDays(monday, -7), addDays(todayKey, -7));
          const d = thisWeek || sameTimeLastWeek ? delta(thisWeek, sameTimeLastWeek, (n) => String(n), false, "this time last week") : { text: null, good: null };
          return (
            <StatTile
              key={`posts-${p}`}
              label={`${NAMES[p]} posts this week`}
              value={`${thisWeek} / 7`}
              delta={d.text}
              deltaGood={d.good}
              trend={weekly.map((w) => (w[p]?.posts as number) ?? 0)}
            />
          );
        })}
        {(["linkedin", "x"] as const).map((p) => {
          const { last, before } = latestEdit(p);
          const isCurrent = last && cur && last.week === cur.week;
          const d = delta(val(last, p, "edit_ratio_median"), val(before, p, "edit_ratio_median"), (n) => `${Math.round(n * 100)} pts`, true, "the week before");
          const series = weekly.map((w) => w[p]?.edit_ratio_median).filter((v): v is number => v != null);
          return (
            <StatTile
              key={`er-${p}`}
              label={`${NAMES[p]} edit ratio (median)`}
              value={pct(val(last, p, "edit_ratio_median"))}
              delta={d.text}
              deltaGood={d.good}
              trend={series}
              hint={last && !isCurrent ? `Week ${wk(last.week)}. Lower means less editing` : "Lower means drafts needed less editing"}
            />
          );
        })}
        <StatTile label="Your pick was #1" value={rank1.length ? pct(rank1.reduce((a, b) => a + b, 0) / rank1.length) : "–"} hint="Last 4 weeks: how often the ranker's top card was the one you chose" />
        {(["linkedin", "x"] as const).map((p) => {
          const now = lastF(p);
          const base = fourWeeksAgo(p);
          return (
            <StatTile
              key={`f-${p}`}
              label={`${NAMES[p]} followers`}
              value={num(now)}
              delta={now != null && base != null && now !== base ? `${now - base > 0 ? "+" : "−"}${num(Math.abs(now - base))} in 4 weeks` : null}
              deltaGood={now != null && base != null ? now >= base : null}
              trend={(followers[p] ?? []).map((r) => r.followers)}
              hint={now == null ? "Add it on the Metrics page" : undefined}
            />
          );
        })}
        <StatTile label="Streak (both platforms)" value={`${stats.streak?.both ?? 0} days`} hint={`LinkedIn ${stats.streak?.linkedin ?? 0} · X ${stats.streak?.x ?? 0}`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {(["linkedin", "x"] as const).map((p) => (
          <ChartCard
            key={`cad-${p}`}
            title={`${NAMES[p]} posts per week`}
            subtitle="Target: 7 a week"
            table={<DataTable columns={["Week", "Posts", "Days posted", "Delivered", "Picked"]} rows={weekly.map((w) => [w.week, num(w[p]?.posts), num(w[p]?.hit_days), num(w[p]?.delivered), num(w[p]?.picked)])} />}
          >
            <ColumnChart labels={labels} values={weekly.map((w) => (w[p]?.posts as number) ?? 0)} color={COLORS[p]} target={7} ariaLabel={`${NAMES[p]} posts per week, last ${weekly.length} weeks`} />
          </ChartCard>
        ))}
      </div>

      <ChartCard
        title="Edit ratio by week"
        subtitle="Median share of each draft you changed before posting. Falling means the drafts are learning your voice."
        legend={<LegendKey items={(["linkedin", "x"] as const).map((p) => ({ label: NAMES[p], color: COLORS[p], kind: "line" as const }))} />}
        table={
          <DataTable
            columns={["Week", "LinkedIn", "X", "Rewrite rate LI", "Rewrite rate X"]}
            rows={weekly.map((w) => [w.week, pct(w.linkedin?.edit_ratio_median), pct(w.x?.edit_ratio_median), pct(w.linkedin?.rewrite_rate), pct(w.x?.rewrite_rate)])}
          />
        }
      >
        <LineChart
          labels={labels}
          series={(["linkedin", "x"] as const).map((p) => ({ key: p, label: NAMES[p], color: COLORS[p], values: weekly.map((w) => (w[p]?.edit_ratio_median as number | null) ?? null) }))}
          format={(v) => pct(v)}
          ariaLabel="Median edit ratio per week for LinkedIn and X"
        />
      </ChartCard>

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard title="Posting days" subtitle="Last 28 days" table={<DataTable columns={["Date", "LinkedIn", "X", "Delivered at"]} rows={days.map((d) => [d.date, d.linkedin, d.x, d.delivered_local ?? "–"])} />}>
          <DaysGrid days={days.map((d) => d.date)} rows={(["linkedin", "x"] as const).map((p) => ({ label: NAMES[p], color: COLORS[p], values: days.map((d) => d[p]) }))} />
        </ChartCard>
        <ChartCard
          title="Pillar mix, last 28 days"
          subtitle="Share of delivered cards; the tick is the starting weight. The learner moves the mix toward what you pick."
          table={
            <DataTable
              columns={["Platform", "Pillar", "Delivered", "Picked", "Posted", "Weight"]}
              rows={(["linkedin", "x"] as const).flatMap((p) =>
                Object.values(mix?.[p] ?? {}).map((r) => [NAMES[p], r.label, r.delivered, r.picked, r.posted, pct(r.weight)]),
              )}
            />
          }
        >
          <div className="grid gap-5 sm:grid-cols-2">
            {(["linkedin", "x"] as const).map((p) => {
              const rows = Object.values(mix?.[p] ?? {});
              const total = rows.reduce((a, r) => a + r.delivered, 0) || 1;
              return (
                <div key={p}>
                  <div className="mb-2 text-[12.5px] font-semibold text-muted">{NAMES[p]}</div>
                  <ShareBars color={COLORS[p]} rows={rows.map((r) => ({ label: r.label, share: r.delivered / total, target: r.weight, detail: `${r.picked} picked` }))} />
                </div>
              );
            })}
          </div>
        </ChartCard>
      </div>

      <Panel title="Rollout gates" description="Each phase closes with a gate you can check here.">
        <ul className="grid gap-2.5 md:grid-cols-2">
          {(stats.gates ?? []).map((g) => (
            <li key={g.gate} className="flex items-start gap-3 rounded-xl border border-border p-3">
              {g.met ? <Check className="mt-0.5 size-5 text-ok" aria-label="Met" /> : <CircleDashed className="mt-0.5 size-5 text-faint" aria-label="Not yet" />}
              <div>
                <div className="text-[13.5px] font-medium">
                  Gate {g.gate}: {g.name}
                </div>
                <div className="text-[12.5px] text-muted">{g.target}</div>
                <div className="mt-0.5 text-[13px] font-semibold">{g.value}</div>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

const SOURCE_TONE: Record<string, Tone> = { seed: "neutral", reflection: "accent", user: "ok", voice: "info" };

function RuleRow({ rule, onRemove, pillar }: { rule: PlaybookRule; onRemove: () => void; pillar: (p: string, k: string) => string }) {
  return (
    <li className="flex items-start gap-3 rounded-xl border border-border p-3">
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px]">{rule.text}</p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <Badge tone={SOURCE_TONE[rule.source ?? "seed"]}>{rule.source === "reflection" ? "Learned" : rule.source === "user" ? "Yours" : rule.source === "voice" ? "Voice" : "Starting rule"}</Badge>
          <Badge tone="neutral">{rule.platform ? NAMES[rule.platform] : "Both platforms"}</Badge>
          {rule.pillar && rule.platform && <Badge tone="neutral">{pillar(rule.platform, rule.pillar)}</Badge>}
          {rule.confidence && rule.source === "reflection" && <Badge tone="neutral">{rule.confidence} confidence</Badge>}
          {rule.evidence?.length ? <Badge tone="neutral">{rule.evidence.length} posts of evidence</Badge> : null}
          {rule.added_in && <Badge tone="neutral">since {rule.added_in}</Badge>}
        </div>
        {rule.reversal && <p className="mt-1 text-[12px] text-muted">Reverses if: {rule.reversal}</p>}
      </div>
      <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" />} aria-label="Remove rule" onClick={onRemove} />
    </li>
  );
}

function PlaybookTab({ view }: { view: DeskState }) {
  const act = useDesk((s) => s.act);
  const pillar = usePillarLabels();
  const tz = useTz();
  const [text, setText] = useState("");
  const [platform, setPlatform] = useState<"" | Platform>("");
  const pb = view.playbook;
  if (!pb) return <Empty title="No playbook yet">It's created on the first run.</Empty>;
  const add = () => {
    if (!text.trim()) return;
    act({ type: "playbook.rule", action: "add", text: text.trim(), platform: platform || null }, { toast: "Rule added. Drafts follow it from the next run." });
    setText("");
  };
  return (
    <div className="space-y-5">
      <Panel title={`Playbook v${pb.version}`} description={pb.summary ?? undefined}>
        <ul className="space-y-2">
          {(pb.rules ?? []).map((r) => (
            <RuleRow key={r.id} rule={r} pillar={pillar} onRemove={() => act({ type: "playbook.rule", action: "remove", rule_id: r.id }, { toast: "Rule removed." })} />
          ))}
        </ul>
        <div className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-[1fr_12rem_auto] sm:items-end">
          <Field label="Add your own rule" htmlFor="pb-new">
            <Textarea id="pb-new" value={text} onChange={(e) => setText(e.target.value)} minRows={1} placeholder='For example "Never end a LinkedIn post with a question".' />
          </Field>
          <Field label="Applies to" htmlFor="pb-plat">
            <Select id="pb-plat" value={platform} onChange={(e) => setPlatform(e.target.value as "" | Platform)}>
              <option value="">Both platforms</option>
              <option value="linkedin">LinkedIn</option>
              <option value="x">X</option>
            </Select>
          </Field>
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={add} disabled={!text.trim()}>
            Add
          </Button>
        </div>
      </Panel>
      <Panel title="Version history">
        <ol className="space-y-2">
          {(view.playbook_history ?? []).map((v) => (
            <li key={v.id} className="rounded-xl border border-border p-3 text-[13px]">
              <div className="flex flex-wrap items-center gap-2">
                <b>v{v.version}</b>
                <span className="text-muted">{formatDate(v.created_at, tz)}</span>
                <Badge tone={v.status === "active" ? "ok" : "neutral"}>{v.status === "active" ? "Active" : "Retired"}</Badge>
                <Badge tone="neutral">{v.source}</Badge>
              </div>
              {v.summary && <p className="mt-1 text-muted">{v.summary}</p>}
              {(v.changes ?? []).length > 0 && (
                <ul className="mt-1 list-disc pl-5">
                  {(v.changes ?? []).slice(0, 6).map((c, i) => (
                    <li key={i}>
                      {String(c.op ?? "change")}
                      {c.text ? `: ${String(c.text)}` : c.rule_id ? ` ${String(c.rule_id)}` : c.count ? ` (${String(c.count)} rules)` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      </Panel>
    </div>
  );
}

function ProposalCard({ p }: { p: Proposal }) {
  const act = useDesk((s) => s.act);
  const tz = useTz();
  const [note, setNote] = useState("");
  const pending = p.status === "pending";
  return (
    <li className="rounded-2xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">{p.title}</p>
          <p className="mt-0.5 text-[12.5px] text-muted">
            {formatDate(p.created_at, tz)} · {p.kind.replace(/_/g, " ")} · {p.confidence} confidence
          </p>
        </div>
        <Badge tone={pending ? "warn" : p.status === "rejected" ? "neutral" : "ok"}>{pending ? "Waiting for you" : p.status}</Badge>
      </div>
      {p.detail && <p className="mt-2 text-[13.5px]">{p.detail}</p>}
      {p.payload && Object.keys(p.payload).length > 0 && (
        <pre className="mt-2 overflow-x-auto rounded-lg bg-surface-2 p-2 text-[11.5px] text-muted">{JSON.stringify(p.payload.patch ?? p.payload, null, 1)}</pre>
      )}
      {pending && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Textarea aria-label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} minRows={1} placeholder="Note (optional)" className="min-w-52 flex-1" />
          <Button variant="primary" icon={<Check className="size-4" />} onClick={() => act({ type: "proposal.decide", proposal_id: p.id, decision: "approve", note: note || null }, { toast: "Approved. It applies on the next run." })}>
            Approve
          </Button>
          <Button icon={<X className="size-4" />} onClick={() => act({ type: "proposal.decide", proposal_id: p.id, decision: "reject", note: note || null }, { toast: "Rejected." })}>
            Reject
          </Button>
        </div>
      )}
    </li>
  );
}

function ProposalsTab({ view }: { view: DeskState }) {
  const proposals = view.proposals ?? [];
  const pending = proposals.filter((p) => p.status === "pending");
  const decided = proposals.filter((p) => p.status !== "pending");
  const experiments = view.experiments ?? [];
  return (
    <div className="space-y-5">
      <section className="space-y-2.5">
        <h2 className="text-[15px] font-semibold">Waiting for you</h2>
        {pending.length === 0 ? (
          <Empty title="Nothing to decide">Changes to pillars, reward weights and guardrails appear here after the weekly review. Everything else the system handles itself.</Empty>
        ) : (
          <ul className="space-y-2.5">
            {pending.map((p) => (
              <ProposalCard key={p.id} p={p} />
            ))}
          </ul>
        )}
      </section>
      <Panel title="Experiments" description="Low-confidence ideas from the weekly review, tried in exploration slots until they're promoted or retired.">
        {experiments.length === 0 ? (
          <p className="text-[13px] text-muted">No experiments yet.</p>
        ) : (
          <DataTable
            columns={["Instruction", "Platform", "Trials", "Picks", "Status"]}
            rows={experiments.map((e) => [e.instruction, e.platform ? NAMES[e.platform] : "Both", e.trials ?? 0, e.picks ?? 0, e.status ?? "active"])}
          />
        )}
      </Panel>
      {decided.length > 0 && (
        <section className="space-y-2.5">
          <h2 className="text-[15px] font-semibold">Decided</h2>
          <ul className="space-y-2.5">
            {decided.map((p) => (
              <ProposalCard key={p.id} p={p} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function ReportTab({ view }: { view: DeskState }) {
  const tz = useTz();
  const r = view.report;
  if (!r) return <Empty title="No weekly report yet">It's written with the first weekly review (Sunday, or Monday morning).</Empty>;
  const s = (r.sections ?? {}) as Record<string, any>;
  const dq = s.drafter_quality ?? {};
  const rh = s.run_health ?? {};
  const ra = s.ranker_accuracy ?? {};
  const g = s.guardrails ?? {};
  const yields = (s.source_yield ?? []) as Array<Record<string, any>>;
  const zero = yields.filter((y) => y.items_28d >= 10 && !y.picked_items_28d);
  return (
    <div className="space-y-5">
      <Panel title={`Week ${r.week}`} description={`Written ${formatDate(r.created_at, tz)}`}>
        <p className="text-[14px]">{s.reflection?.summary ?? "No reflection summary."}</p>
        {(r.actions ?? []).length > 0 && (
          <div className="mt-3">
            <div className="text-[13px] font-semibold">Changes the system made itself</div>
            <ul className="mt-1 list-disc pl-5 text-[13px]">
              {(r.actions ?? []).map((a, i) => (
                <li key={i}>
                  {a.type === "pause_source" ? `Paused source ${a.source_id}: ${a.reason}` : a.type === "explore_rate" ? `Exploration ${pct(a.from as number)} → ${pct(a.to as number)} (${a.reason})` : `Candidates from ${a.scout}: ${a.from} → ${a.to}`}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Top-ranked card picked" value={pct(ra.accuracy)} hint={`${ra.deliveries_with_pick ?? 0} deliveries with a pick · mean pick rank ${num(ra.mean_pick_rank)}`} />
        <StatTile label="Rewrite rate" value={pct(dq.rewrite_rate)} hint="Cards sent back at least once" />
        <StatTile label="Guardrail catches" value={num((g.blocked ?? 0) + (g.unsourced ?? 0) + (g.first_person ?? 0))} hint={`${g.blocked ?? 0} blocked · ${g.unsourced ?? 0} unsourced · ${g.first_person ?? 0} first-person`} />
        <StatTile label="Runs" value={`${num(rh.runs)}`} hint={`${rh.failed ?? 0} failed · ${rh.late_deliveries ?? 0} late · ${rh.llm_calls ?? 0} model calls`} />
      </div>
      <Panel title="Drafter quality by prompt version" description="Edit ratio per version: how the system tells whether a change helped.">
        <DataTable columns={["Prompt version", "Posts", "Median edit ratio"]} rows={Object.entries((dq.by_prompt_version ?? {}) as Record<string, { n: number; edit_ratio_median: number | null }>).map(([k, v]) => [k, v.n, pct(v.edit_ratio_median)])} />
      </Panel>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Scout hit rate">
          <DataTable columns={["Scout", "Delivered", "Picked", "Rate"]} rows={((s.scout_hit_rate ?? []) as Array<Record<string, any>>).map((x) => [x.scout, x.delivered, x.picked, pct(x.rate)])} />
        </Panel>
        <Panel title="Model calls by provider">
          <DataTable columns={["Provider", "Calls"]} rows={Object.entries((rh.llm_by_provider ?? {}) as Record<string, number>).map(([k, v]) => [k, v])} />
          {(rh.quota_exhausted ?? []).length > 0 && <p className="mt-2 text-[12.5px] text-warn">Quota reached: {(rh.quota_exhausted as string[]).join(", ")}</p>}
        </Panel>
      </div>
      <Panel title="Source yield (28 days)" description={zero.length ? `${zero.length} sources produced items but no picked cards.` : "Share of each source's items that ended up in cards you picked."}>
        <DataTable columns={["Source", "Scout", "Items", "Picked", "Yield"]} rows={yields.slice(0, 15).map((y) => [y.name, y.scout, y.items_28d, y.picked_items_28d, pct(y.yield)])} />
      </Panel>
    </div>
  );
}

function VoiceTab({ view }: { view: DeskState }) {
  const act = useDesk((s) => s.act);
  const [phrase, setPhrase] = useState("");
  const v = view.voice;
  const settingsAvoid = ((view.settings as Record<string, any>)?.voice?.avoid_phrases ?? []) as string[];
  const addAvoid = () => {
    const p = phrase.trim();
    if (!p) return;
    act({ type: "settings.update", patch: { voice: { avoid_phrases: [...settingsAvoid, p] } } }, { toast: `"${p}" added to the avoid list.` });
    setPhrase("");
  };
  const stats = (v?.stats ?? {}) as Record<string, Record<string, any>>;
  return (
    <div className="space-y-5">
      <Panel title={v ? `Voice profile v${v.version}` : "Voice profile"} description={v?.summary ?? "Learns from your edits from day one. Drafts read more generic for the first two or three weeks."}>
        {v?.rules?.length ? (
          <ul className="list-disc space-y-1 pl-5 text-[13.5px]">
            {v.rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-muted">No rules yet. They appear after a few posts.</p>
        )}
      </Panel>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Phrases you cut" description="Cut from two or more drafts: these join the avoid list automatically.">
          {(v?.cut_phrases ?? []).length ? (
            <DataTable columns={["Phrase", "Times cut"]} rows={(v?.cut_phrases ?? []).map((c) => [String(c.phrase), String(c.count)])} />
          ) : (
            <p className="text-[13px] text-muted">Nothing yet.</p>
          )}
        </Panel>
        <Panel title="Avoid list" description="Drafts never use these. Add your own.">
          <div className="flex flex-wrap gap-1.5">
            {[...new Set([...settingsAvoid, ...(v?.avoid ?? [])])].map((p) => (
              <Badge key={p} tone="neutral">
                {p}
              </Badge>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <input
              aria-label="Phrase to avoid"
              value={phrase}
              onChange={(e) => setPhrase(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addAvoid()}
              placeholder="Add a phrase"
              className="h-9 flex-1 rounded-lg border border-border bg-surface px-3 text-sm"
            />
            <Button size="sm" onClick={addAvoid} disabled={!phrase.trim()}>
              Add
            </Button>
          </div>
        </Panel>
      </div>
      <Panel title="Writing statistics (last 60 days)">
        <DataTable
          columns={["Platform", "Posts", "Median length", "Draft length", "Words / sentence", "Emoji / post", "Hashtags / post", "Edit ratio"]}
          rows={(["linkedin", "x"] as const)
            .filter((p) => stats[p])
            .map((p) => [NAMES[p], num(stats[p].posts), num(stats[p].final_length_median), num(stats[p].draft_length_median), num(stats[p].sentence_words_median), num(stats[p].emoji_per_post), num(stats[p].hashtags_per_post), pct(stats[p].edit_ratio_median)])}
        />
      </Panel>
    </div>
  );
}

type FeedbackRow = { at?: string | null; card_id: string; title: string; platform: Platform; pillar: string; reason?: string | null; note?: string | null };
const TOPIC_REASONS = new Set(["not_interesting", "off_brand", "too_risky", "other"]);

/** Skip reasons the ranking learns from: the pipeline's list plus skips made on this device since the last run. */
function useFeedback(view: DeskState): FeedbackRow[] {
  return useMemo(() => {
    const rows = new Map<string, FeedbackRow>();
    for (const r of (((view.stats ?? {}) as { feedback?: FeedbackRow[] }).feedback ?? [])) rows.set(r.card_id, r);
    for (const c of view.cards ?? []) {
      if (c.status !== "skipped" || !c.skip || !(TOPIC_REASONS.has(c.skip.reason) || c.skip.note)) continue;
      rows.set(c.id, { at: c.skip.at ?? c.status_changed_at, card_id: c.id, title: c.title, platform: c.platform, pillar: c.pillar, reason: c.skip.reason, note: c.skip.note });
    }
    return [...rows.values()].sort((a, b) => (b.at ?? "").localeCompare(a.at ?? "")).slice(0, 15);
  }, [view]);
}

function FeedbackPanel({ view }: { view: DeskState }) {
  const tz = useTz();
  const pillar = usePillarLabels();
  const rows = useFeedback(view);
  return (
    <Panel
      title="Your recent feedback"
      description="Skips with a reason from the last 30 days. The next morning's ranking reads them (your own words count most), similar topics rank lower, and the weekly review uses them to adjust the playbook."
    >
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No skip reasons yet. When you skip a card, pick a reason; for "Other", say why.</p>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((r) => (
            <li key={r.card_id} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2.5 text-[13.5px]">
              <PlatformMark platform={r.platform} className="mt-0.5 size-4 text-[9px]" />
              <div className="min-w-0 flex-1">
                <Link to={`/card/${r.card_id}`} className="font-medium hover:underline">
                  {r.title}
                </Link>
                <div className="text-[12.5px] text-muted">
                  {r.at ? formatDate(r.at, tz) : ""} · {pillar(r.platform, r.pillar)}
                </div>
                {r.note && <p className="mt-1 text-text/90">“{r.note}”</p>}
              </div>
              <Badge tone="neutral">{SKIP_REASONS.find((x) => x.value === r.reason)?.label ?? r.reason ?? "Skipped"}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function LearningTab({ view }: { view: DeskState }) {
  const pillar = usePillarLabels();
  const arms = view.arms ?? [];
  const shares = useMemo(() => {
    const out: Record<string, number> = {};
    for (const p of ["linkedin", "x"] as const) {
      const strategy = ((view.settings as Record<string, any>)?.strategy?.[p] ?? {}) as Record<string, { weight: number }>;
      const total = Object.values(strategy).reduce((a, s) => a + (s.weight ?? 0), 0) || 1;
      const raw: Record<string, number> = {};
      for (const [k, s] of Object.entries(strategy)) {
        const own = arms.filter((a) => a.platform === p && a.pillar === k);
        const a = own.reduce((x, r) => x + r.alpha, 0);
        const b = own.reduce((x, r) => x + r.beta, 0);
        const prior = own.length ? own.reduce((x, r) => x + r.prior_mean, 0) / own.length : 0.5;
        raw[k] = (s.weight / total) * (own.length ? a / (a + b) / prior : 1);
      }
      const sum = Object.values(raw).reduce((x, y) => x + y, 0) || 1;
      for (const [k, v] of Object.entries(raw)) out[`${p}:${k}`] = v / sum;
    }
    return out;
  }, [arms, view.settings]);
  return (
    <div className="space-y-5">
      <FeedbackPanel view={view} />
      <Panel title="How the mix is chosen" description="Each pillar × format is an arm. Picks and posts raise an arm, skips lower it (except 'wrong timing' and 'already covered'), and old results fade with a six-week half-life. About 20% of slots explore.">
        <div className="-mx-4 overflow-x-auto px-4">
          <DataTable
            columns={["Arm", "Evidence (weighted)", "Estimate", "Starting prior", "Current target share"]}
            rows={arms
              .slice()
              .sort((a, b) => a.platform.localeCompare(b.platform) || b.mean - a.mean)
              .map((a) => [
                `${NAMES[a.platform]} · ${pillar(a.platform, a.pillar)} · ${a.format.replace(/^(li|x)_/, "")}`,
                num(a.n_obs),
                pct(a.mean),
                pct(a.prior_mean),
                pct(shares[`${a.platform}:${a.pillar}`]),
              ])}
          />
        </div>
      </Panel>
    </div>
  );
}

type Tab = "overview" | "playbook" | "proposals" | "report" | "voice" | "learning";

export function Insights() {
  const view = useDesk((s) => s.view);
  const route = useRoute();
  const tab = (route.query.get("tab") as Tab) || "overview";
  const setTab = (t: Tab) => navigate(`/insights?tab=${t}`, { replace: true });
  if (!view) return <Empty title="No data yet">Insights appear after the first runs.</Empty>;
  const pendingProps = (view.proposals ?? []).filter((p) => p.status === "pending").length;
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
        <p className="mt-1 text-sm text-muted">How your posting is going, and how the system is learning from it.</p>
      </header>
      <Tabs
        label="Insights sections"
        value={tab}
        onChange={setTab}
        items={[
          { value: "overview", label: "Overview" },
          { value: "playbook", label: "Playbook" },
          { value: "proposals", label: "Proposals", count: pendingProps },
          { value: "report", label: "Weekly report" },
          { value: "voice", label: "Voice" },
          { value: "learning", label: "Learning" },
        ]}
      />
      {tab === "overview" && <Overview view={view} />}
      {tab === "playbook" && <PlaybookTab view={view} />}
      {tab === "proposals" && <ProposalsTab view={view} />}
      {tab === "report" && <ReportTab view={view} />}
      {tab === "voice" && <VoiceTab view={view} />}
      {tab === "learning" && <LearningTab view={view} />}
    </div>
  );
}
