import { ExternalLink, HeartHandshake, Search } from "lucide-react";
import type { Card } from "@/types";
import { AFFAIRS_LABEL, FORMAT_LABEL, pct } from "@/lib/format";
import { safeUrl, xProfileUrl, xSearchUrl } from "@/lib/compose";
import { editSummary, tellName } from "@/lib/guard";
import { formatDateTime } from "@/lib/time";
import { useTz } from "@/state/hooks";
import { Badge } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="text-[12px] font-semibold tracking-wide text-muted uppercase">{title}</h3>
      {children}
    </section>
  );
}

export function WhyAngle({ card }: { card: Card }) {
  return (
    <div className="space-y-4">
      {card.why_now && (
        <Block title="Why now">
          <p className="text-[13.5px] leading-relaxed">{card.why_now}</p>
        </Block>
      )}
      {card.angle && (
        <Block title="Proposed angle">
          <p className="text-[13.5px] leading-relaxed">{card.angle}</p>
          {card.mode === "external" && <p className="text-xs text-muted">A suggestion: it becomes your view only if you post it.</p>}
        </Block>
      )}
      {card.affairs_type && (
        <Block title="Affairs post type">
          <Badge tone="info">{AFFAIRS_LABEL[card.affairs_type] ?? card.affairs_type}</Badge>
        </Block>
      )}
      {card.format_note && (
        <Block title="Format idea">
          <p className="text-[13.5px] leading-relaxed">{card.format_note}</p>
        </Block>
      )}
      {card.flags?.sensitive && (
        <div className="flex gap-2 rounded-xl border border-info/30 bg-info-soft p-3 text-[13px]">
          <HeartHandshake className="mt-0.5 size-4 shrink-0 text-info" />
          <p>
            <b>Handle with care.</b> {card.flags.sensitive_reason ? `This topic ${card.flags.sensitive_reason}.` : ""} Keep it factual and humane: no hot
            takes, no engagement questions.
          </p>
        </div>
      )}
    </div>
  );
}

export function ReplyHelper({ card }: { card: Card }) {
  const reply = card.draft?.reply;
  if (card.format !== "x_reply" && card.format !== "x_quote") return null;
  const terms = reply?.search_terms?.length ? reply.search_terms : card.title.split(/\s+/).slice(0, 4);
  const accounts = reply?.accounts ?? [];
  const quoteUrl = safeUrl(card.draft?.quote_url);
  return (
    <div className="space-y-2.5 rounded-2xl border border-accent/25 bg-accent-soft/40 p-3.5">
      <h3 className="text-[13px] font-semibold">{card.format === "x_reply" ? "Find the thread to reply to" : "Find the post to quote"}</h3>
      {reply?.context && <p className="text-[13px] text-muted">{reply.context}</p>}
      <div className="flex flex-wrap gap-2">
        <LinkButton size="sm" variant="primary" href={xSearchUrl(terms, accounts)} target="_blank" rel="noreferrer" icon={<Search className="size-4" />}>
          Search X{accounts.length ? " (watchlist)" : ""}
        </LinkButton>
        <LinkButton size="sm" href={xSearchUrl(terms)} target="_blank" rel="noreferrer" icon={<Search className="size-4" />}>
          Search all of X
        </LinkButton>
        {quoteUrl && (
          <LinkButton size="sm" href={quoteUrl} target="_blank" rel="noreferrer" icon={<ExternalLink className="size-4" />}>
            Source
          </LinkButton>
        )}
      </div>
      {accounts.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {accounts.map((a) => (
            <a key={a} href={xProfileUrl(a)} target="_blank" rel="noreferrer" className="rounded-md bg-surface px-1.5 py-0.5 text-[12px] text-accent hover:underline">
              @{a.replace(/^@/, "")}
            </a>
          ))}
        </div>
      )}
      <p className="text-xs text-muted">Replying to large accounts is how a small account gets seen. Keep it specific and generous.</p>
    </div>
  );
}

export function Sources({ card }: { card: Card }) {
  const tz = useTz();
  const sources = card.sources ?? [];
  const claims = card.claims ?? [];
  if (!sources.length) {
    return <p className="text-[13px] text-muted">{card.mode === "interview" ? "Interview card: the draft uses only your answers." : "No sources on this card."}</p>;
  }
  return (
    <ol className="space-y-2.5">
      {sources.map((s, i) => {
        const url = safeUrl(s.url);
        const mine = claims.filter((c) => c.source === i);
        return (
          <li key={i} className="rounded-xl border border-border p-2.5">
            <div className="flex items-start gap-2">
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded bg-surface-3 text-[11px] font-semibold text-muted">{i + 1}</span>
              <div className="min-w-0">
                {url ? (
                  <a href={url} target="_blank" rel="noreferrer" className="text-[13.5px] leading-snug font-medium text-accent hover:underline">
                    {s.title || url}
                  </a>
                ) : (
                  <span className="text-[13.5px] font-medium">{s.title}</span>
                )}
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
                  {s.publisher && <span>{s.publisher}</span>}
                  {s.published_at && <span>· {formatDateTime(s.published_at, tz)}</span>}
                  {s.lang === "hi" && <Badge tone="info">Hindi original</Badge>}
                </div>
                {s.orig_title && <p className="mt-1 text-[13px] text-muted" lang="hi">{s.orig_title}</p>}
                {s.summary && <p className="mt-1 line-clamp-3 text-[12.5px] text-muted">{s.summary}</p>}
                {mine.length > 0 && (
                  <ul className="mt-1.5 space-y-0.5 border-l-2 border-accent/40 pl-2 text-[12.5px]">
                    {mine.map((c, j) => (
                      <li key={j}>“{c.text}”</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function PipelineFlags({ card }: { card: Card }) {
  const f = card.flags ?? {};
  const rows: Array<{ tone: "bad" | "warn" | "info"; title: string; items: string[] }> = [
    { tone: "bad", title: "Blocked: matches your blocklist", items: f.blocked ?? [] },
    { tone: "warn", title: "Figures not found in the sources", items: f.unsourced ?? [] },
    { tone: "warn", title: "First-person claims (you didn't provide these)", items: f.first_person ?? [] },
    { tone: "info", title: "Opinion framing — make sure you agree", items: f.opinion ?? [] },
    { tone: "warn", title: "Phrases you avoid", items: f.avoid_phrases ?? [] },
    { tone: "warn", title: "Engagement bait", items: f.bait ?? [] },
    { tone: "warn", title: "Length", items: f.length ?? [] },
    { tone: "warn", title: "Sounds like AI", items: (f.ai_tells ?? []).map((t) => `${tellName(t.kind)}: “${t.text}”`) },
    { tone: "info", title: "Notes", items: f.notes ?? [] },
  ].filter((r) => r.items.length) as Array<{ tone: "bad" | "warn" | "info"; title: string; items: string[] }>;
  if (!rows.length) return <p className="text-[13px] text-ok">The pipeline's checks found nothing to flag.</p>;
  const tone = { bad: "border-bad/30 bg-bad-soft text-bad", warn: "border-warn/30 bg-warn-soft text-warn", info: "border-info/30 bg-info-soft text-info" };
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.title} className={`rounded-xl border px-3 py-2 text-[13px] ${tone[r.tone]}`}>
          <div className="font-medium">{r.title}</div>
          <ul className="mt-0.5 list-disc pl-4 text-text">
            {r.items.map((it) => (
              <li key={it}>{it}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function Details({ card }: { card: Card }) {
  const tz = useTz();
  const parts = (card.score_parts ?? {}) as Record<string, number>;
  const rows: Array<[string, React.ReactNode]> = [
    ["Format", FORMAT_LABEL[card.format]],
    ["Mode", card.mode === "interview" ? "Interview (drafted only from your answers)" : "External (drafted from sources)"],
    ["Rank", card.rank ?? "–"],
    ["Slot", card.explore ? (card.experiment_id ? "Experiment" : "Exploration") : "Best guess"],
    ["Arm", card.arm ?? "–"],
    ["Fit / timeliness / momentum / novelty", ["fit", "timeliness", "momentum", "novelty"].map((k) => (parts[k] != null ? pct(parts[k]) : "–")).join(" · ")],
    ["Angle potential", parts.angle_potential != null ? `${parts.angle_potential}/5` : "–"],
    ["Rewrites", card.rewrite_count ?? 0],
    ["Written by", card.llm ? `${card.llm.model} (${card.llm.provider})` : "–"],
    ["Editor pass", editSummary(card.llm?.edit) ?? "–"],
    ["Versions", [card.versions?.playbook && `playbook ${card.versions.playbook}`, card.versions?.voice && `voice ${card.versions.voice}`, card.versions?.prompt && `prompt ${card.versions.prompt}`].filter(Boolean).join(" · ") || "–"],
    ["Delivered", formatDateTime(card.delivered_at ?? card.created_at, tz)],
    ["Expires", card.expires_at ? formatDateTime(card.expires_at, tz) : "–"],
  ];
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[13px]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
