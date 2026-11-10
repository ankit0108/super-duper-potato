import { useState } from "react";
import { ExternalLink, PenLine, Telescope } from "lucide-react";
import type { Platform } from "@/types";
import { FORMAT_LABEL, PLATFORM_LABEL, pct } from "@/lib/format";
import { safeUrl } from "@/lib/compose";
import { Link } from "@/lib/router";
import { EVIDENCE_LABEL, PENDING_CARD, RISK_LABEL, WINDOW_LABEL, markRows, reportsFor, searchLine, type Opportunity, type ScoutNote, type ScoutReport } from "@/lib/scouts";
import { dayLabel } from "@/lib/save";
import { useDesk } from "@/state/store";
import { usePillarLabels, useView } from "@/state/hooks";
import { Badge } from "@/components/ui/Badge";
import { Button, cx } from "@/components/ui/Button";
import { Banner, Empty, Panel } from "@/components/ui/Feedback";
import { Select } from "@/components/ui/Field";
import { Segmented } from "@/components/ui/Tabs";

/** The scout's six marks, each out of 3. */
export function Marks({ marks }: { marks: ScoutNote["marks"] }) {
  const rows = markRows(marks as Record<string, number> | undefined);
  if (!rows.length) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-muted" aria-label="The scout's marks, each out of 3">
      {rows.map((m) => (
        <li key={m.key} className="flex items-center gap-1.5">
          <span>{m.label}</span>
          <span className="flex gap-0.5" aria-hidden>
            {[1, 2, 3].map((i) => (
              <span key={i} className={cx("size-1.5 rounded-full", i <= m.value ? "bg-accent" : "bg-border-strong")} />
            ))}
          </span>
          <span className="sr-only">{m.value} of 3</span>
        </li>
      ))}
    </ul>
  );
}

/** A scout's read of a story: the evidence first, then its guess, labelled as one. Used here and on the card page. */
export function ScoutRead({ note, platform }: { note: ScoutNote; platform: Platform }) {
  const ev = EVIDENCE_LABEL[note.evidence_level ?? "hypothesis"] ?? EVIDENCE_LABEL.hypothesis;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={ev.tone} title={ev.hint}>
          {ev.label}
        </Badge>
        {note.window && <Badge tone="neutral">{WINDOW_LABEL[note.window] ?? note.window}</Badge>}
        {note.risk && <Badge tone="warn">{RISK_LABEL[note.risk] ?? note.risk}</Badge>}
        {note.visual && <Badge tone="info">Could be a {note.visual}</Badge>}
        {!!note.score && <span className="text-[12.5px] text-muted">Scout's score {pct(note.score)}</span>}
      </div>
      {!!note.evidence?.length && (
        <ul className="list-disc space-y-0.5 pl-5 text-[13px]">
          {note.evidence.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {note.why && (
        <p className="text-[13.5px] leading-relaxed">
          <span className="font-medium">Why it could travel on {PLATFORM_LABEL[platform]} (the scout's guess, not a measurement):</span> {note.why}
        </p>
      )}
      {note.opening && (
        <p className="text-[13.5px] leading-relaxed">
          <span className="font-medium">Opening direction:</span> {note.opening}
        </p>
      )}
      {note.reply_to && (
        <p className="text-[13.5px] leading-relaxed">
          <span className="font-medium">Who to reply to:</span> {note.reply_to}
        </p>
      )}
      <Marks marks={note.marks} />
    </div>
  );
}

function OpportunityRow({ report, opp }: { report: ScoutReport; opp: Opportunity }) {
  const act = useDesk((s) => s.act);
  const view = useView();
  const pillar = usePillarLabels();
  const card = opp.card_id && opp.card_id !== PENDING_CARD ? view?.cards?.find((c) => c.id === opp.card_id) : undefined;
  const url = safeUrl(opp.url);
  return (
    <li className="space-y-2 py-4 first:pt-0 last:pb-0" data-testid="scout-opportunity">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[15px] leading-snug font-semibold">
            <span className="mr-1.5 text-muted">{opp.rank}.</span>
            {opp.title}
          </h3>
          <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[12.5px] text-muted">
            {opp.lane && <span>{pillar(report.platform, opp.lane)}</span>}
            {opp.format && <span>· {FORMAT_LABEL[opp.format as keyof typeof FORMAT_LABEL] ?? opp.format}</span>}
            {url && (
              <a className="inline-flex items-center gap-1 underline underline-offset-2" href={url} target="_blank" rel="noreferrer">
                Source <ExternalLink className="size-3" />
              </a>
            )}
          </p>
        </div>
        {card ? (
          <Link to={`/card/${encodeURIComponent(card.id)}`} className="text-[13px] font-medium text-accent underline underline-offset-2">
            Open the card
          </Link>
        ) : opp.card_id ? (
          <span className="text-[13px] text-muted">{opp.card_id === PENDING_CARD ? "Drafting: it will be on the board in a few minutes" : "Drafted earlier"}</span>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            icon={<PenLine className="size-4" />}
            onClick={() => act({ type: "scout.draft", report_id: report.id, topic_id: opp.id }, { toast: "Drafting it now: the card will be on the board in a few minutes." })}
          >
            Draft this
          </Button>
        )}
      </div>
      {opp.angle && <p className="text-[13.5px] leading-relaxed text-muted">{opp.angle}</p>}
      <ScoutRead note={opp} platform={report.platform} />
    </li>
  );
}

function Report({ report }: { report: ScoutReport }) {
  const opps = report.opportunities ?? [];
  const passed = report.passed ?? [];
  const probes = report.probes ?? [];
  return (
    <div className="space-y-4">
      {report.status !== "ok" && <Banner tone="warn">{report.error || report.note || "The scout wrote no report this day."}</Banner>}
      {report.status === "ok" && report.note && <p className="text-[14px] leading-relaxed">{report.note}</p>}
      {opps.length > 0 ? (
        <Panel title={`Opportunities (${opps.length})`} description="Ranked by the scout. Evidence is what a public site reported or a search found; the rest is the scout's read.">
          <ul className="divide-y divide-border">
            {opps.map((o) => (
              <OpportunityRow key={o.id} report={report} opp={o} />
            ))}
          </ul>
        </Panel>
      ) : (
        report.status === "ok" && <Empty title="No opportunities this day">The scout found nothing it would post about.</Empty>
      )}
      {passed.length > 0 && (
        <Panel title={`Passed on (${passed.length})`} description="Stories the scout read and wouldn't post about, with its reason.">
          <ul className="space-y-2 text-[13.5px]">
            {passed.map((p) => (
              <li key={p.id}>
                <span className="font-medium">{p.title}</span>
                {p.reason && <span className="text-muted">: {p.reason}</span>}
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {probes.length > 0 && (
        <Panel title="Searches it ran" description="A search result shows a page exists, not how it performed.">
          <ul className="space-y-1 text-[13.5px]">
            {probes.map((p) => (
              <li key={`${p.where}:${p.query}`}>
                “{p.query}” <span className="text-muted">on {p.where === "web" ? "the web" : PLATFORM_LABEL[p.where as Platform]}: {p.found} found</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {report.model && <p className="text-xs text-muted">Written by {report.model}.</p>}
    </div>
  );
}

export function Scouts() {
  const view = useView();
  const [platform, setPlatform] = useState<Platform>("linkedin");
  const [day, setDay] = useState<string | null>(null);
  const reports = reportsFor(view?.scouts, platform);
  const report = reports.find((r) => r.local_date === day) ?? reports[0];
  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Scouts</h1>
        <p className="max-w-2xl text-sm text-muted">
          Each morning a LinkedIn scout and an X scout read the day's stories and report what's worth posting on their platform, with the evidence. Their marks move stories up or down
          in your morning set; your lane mix stays yours.
        </p>
      </header>
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          label="Platform"
          value={platform}
          onChange={(p) => {
            setPlatform(p);
            setDay(null);
          }}
          items={[
            { value: "linkedin", label: "LinkedIn scout" },
            { value: "x", label: "X scout" },
          ]}
        />
        {reports.length > 1 && (
          <Select aria-label="Report day" value={report?.local_date ?? ""} onChange={(e) => setDay(e.target.value)} className="w-auto">
            {reports.map((r) => (
              <option key={r.id} value={r.local_date}>
                {dayLabel(r.local_date)}
              </option>
            ))}
          </Select>
        )}
      </div>
      <p className="text-[13px] text-muted">{searchLine(view?.scout_search)}</p>
      {report ? (
        <Report report={report} />
      ) : (
        <Empty icon={<Telescope className="size-6" />} title="No report yet">
          The {PLATFORM_LABEL[platform]} scout writes its first report with the next morning set.
        </Empty>
      )}
    </div>
  );
}
