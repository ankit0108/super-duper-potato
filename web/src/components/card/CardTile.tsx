import type { KeyboardEvent, ReactNode } from "react";
import { Compass, FlaskConical, Loader2, MessageCircleQuestion, OctagonAlert, ShieldAlert, Sigma, UserRound, HeartHandshake, Ruler } from "lucide-react";
import type { Card, SkipReason } from "@/types";
import { FORMAT_LABEL, SKIP_REASONS, draftText } from "@/lib/format";
import { navigate } from "@/lib/router";
import { useDesk } from "@/state/store";
import { usePillarLabels } from "@/state/hooks";
import { Badge, PlatformMark, StatusBadge } from "../ui/Badge";
import { Button, cx } from "../ui/Button";
import { Menu } from "../ui/Menu";

export function workLabel(card: Card): string | null {
  if (!card.work) return null;
  if (card.work.kind === "rewrite") return card.work.target_platform && card.work.target_platform !== card.platform ? "Adapting…" : "Rewriting…";
  if (card.work.kind === "questions") return "Preparing questions…";
  return (card.answers?.length ?? 0) > 0 ? "Drafting from your answers…" : "Drafting…";
}

export function FlagIcons({ card }: { card: Card }) {
  const f = card.flags ?? {};
  const items: Array<{ show: boolean; icon: ReactNode; label: string; tone: string }> = [
    { show: !!f.blocked?.length, icon: <ShieldAlert className="size-3.5" />, label: `Blocked: matches your blocklist (${f.blocked?.length})`, tone: "text-bad" },
    { show: !!f.unsourced?.length, icon: <Sigma className="size-3.5" />, label: `${f.unsourced?.length} figure(s) not found in the sources`, tone: "text-warn" },
    { show: !!f.first_person?.length, icon: <UserRound className="size-3.5" />, label: "First-person claim in an external draft", tone: "text-warn" },
    { show: !!f.sensitive, icon: <HeartHandshake className="size-3.5" />, label: `Handle with care${f.sensitive_reason ? `: ${f.sensitive_reason}` : ""}`, tone: "text-info" },
    { show: !!f.length?.length, icon: <Ruler className="size-3.5" />, label: f.length?.join("; ") ?? "", tone: "text-warn" },
    { show: !!(f.bait?.length || f.avoid_phrases?.length), icon: <OctagonAlert className="size-3.5" />, label: "Contains phrases you avoid", tone: "text-warn" },
  ];
  const shown = items.filter((i) => i.show);
  if (!shown.length) return null;
  return (
    <span className="flex items-center gap-1.5">
      {shown.map((i) => (
        <span key={i.label} title={i.label} aria-label={i.label} className={i.tone}>
          {i.icon}
        </span>
      ))}
    </span>
  );
}

export function SkipMenu({ card, size = "sm" }: { card: Card; size?: "sm" | "md" }) {
  const act = useDesk((s) => s.act);
  const skip = (reason: SkipReason) => act({ type: "card.skip", card_id: card.id, reason }, { toast: "Skipped. The ranker will learn from this." });
  return (
    <Menu
      label="Skip reasons"
      trigger={(p) => (
        <Button size={size} variant="ghost" {...p} onClick={(e) => { e.stopPropagation(); p.onClick(); }}>
          Skip
        </Button>
      )}
      items={SKIP_REASONS.map((r) => ({ label: r.label, hint: r.help, onSelect: () => skip(r.value) }))}
    />
  );
}

export function CardTile({ card, pending }: { card: Card; pending?: boolean }) {
  const pillar = usePillarLabels();
  const work = workLabel(card);
  const text = draftText(card);
  const open = () => navigate(`/card/${card.id}`);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" && e.target === e.currentTarget) open();
  };
  const brief = card.draft_state === "brief";
  const questions = card.status === "needs_input" ? card.questions?.length ?? 0 : 0;
  return (
    <article
      data-tile
      tabIndex={0}
      onKeyDown={onKey}
      onClick={open}
      aria-label={`${card.platform === "x" ? "X" : "LinkedIn"} card: ${card.title}`}
      className={cx(
        "group cursor-pointer rounded-2xl border bg-surface p-3.5 transition-shadow hover:shadow-md focus-visible:shadow-md",
        card.status === "blocked" ? "border-bad/40" : card.status === "needs_input" ? "border-warn/40" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <PlatformMark platform={card.platform} />
        {card.rank != null && card.kind === "news" && <span className="text-[12px] font-semibold tabular-nums text-muted">#{card.rank}</span>}
        <Badge tone="neutral">{pillar(card.platform, card.pillar)}</Badge>
        <Badge tone="neutral">{FORMAT_LABEL[card.format]}</Badge>
        {card.kind && card.kind !== "news" && <Badge tone="info">{card.kind === "adapt" ? "Adapted" : card.kind[0].toUpperCase() + card.kind.slice(1)}</Badge>}
        {card.explore && (
          <Badge tone="accent" icon={card.experiment_id ? <FlaskConical className="size-3" /> : <Compass className="size-3" />} title={card.experiment_id ? "An experiment the weekly review is testing" : "An exploration slot: the system is testing this mix"}>
            {card.experiment_id ? "Experiment" : "Exploring"}
          </Badge>
        )}
        {card.status !== "suggested" && <StatusBadge status={card.status} />}
        {pending && <Badge tone="neutral">Syncing</Badge>}
        <span className="ml-auto">
          <FlagIcons card={card} />
        </span>
      </div>
      <h3 className="mt-2 line-clamp-2 text-[15px] leading-snug font-semibold">{card.title}</h3>
      {card.why_now && <p className="mt-1 line-clamp-1 text-[13px] text-muted">{card.why_now}</p>}
      <div className="mt-2.5 min-h-[3.2rem] rounded-xl bg-surface-2 px-3 py-2 text-[13.5px] leading-relaxed text-text/90">
        {work ? (
          <span className="flex items-center gap-2 text-accent">
            <Loader2 className="size-4 animate-spin" /> {work}
          </span>
        ) : questions ? (
          <span className="flex items-start gap-2 text-warn">
            <MessageCircleQuestion className="mt-0.5 size-4 shrink-0" />
            <span>
              {questions} question{questions === 1 ? "" : "s"} for you: <span className="text-text">{card.questions?.[0]?.q}</span>
            </span>
          </span>
        ) : brief ? (
          <span className="text-muted">Draft skipped (model quota). Open it and tap <b>Draft this</b>, or write it yourself from the angle: {card.angle}</span>
        ) : (
          <p className="line-clamp-3 whitespace-pre-line">{text || card.angle}</p>
        )}
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2" onClick={(e) => e.stopPropagation()}>
        <span className="truncate text-[12px] text-faint">{card.angle && !brief ? `Angle: ${card.angle}` : ""}</span>
        <div className="flex shrink-0 items-center gap-1">
          {["suggested", "needs_input", "blocked", "editing"].includes(card.status) && <SkipMenu card={card} />}
          <Button size="sm" variant={card.status === "needs_input" ? "primary" : "secondary"} onClick={open}>
            {card.status === "needs_input" ? "Answer" : card.status === "blocked" ? "Review" : card.status === "editing" ? "Continue" : "Open"}
          </Button>
        </div>
      </div>
    </article>
  );
}
