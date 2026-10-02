import type { KeyboardEvent, ReactNode } from "react";
import { Bot, Compass, FlaskConical, Loader2, MessageCircleQuestion, OctagonAlert, ShieldAlert, Sigma, UserRound, HeartHandshake, Ruler } from "lucide-react";
import type { Card } from "@/types";
import { FORMAT_LABEL, MENU_SKIP_REASONS, PLATFORM_LABEL, draftText } from "@/lib/format";
import { tellSummary } from "@/lib/guard";
import { navigate } from "@/lib/router";
import { useDesk } from "@/state/store";
import { useNow, usePillarLabels } from "@/state/hooks";
import { Badge, PlatformMark, StatusBadge } from "../ui/Badge";
import { Button, cx } from "../ui/Button";
import { Menu } from "../ui/Menu";

export function workLabel(card: Card): string | null {
  if (!card.work) return null;
  if (card.work.kind === "rewrite" && card.work.target_platform && card.work.target_platform !== card.platform)
    return card.work.crosspost === "switch" ? `Moving to ${PLATFORM_LABEL[card.work.target_platform]}…` : `Making the ${PLATFORM_LABEL[card.work.target_platform]} version…`;
  if (card.work.kind === "rewrite") return "Rewriting…";
  if (card.work.kind === "visual") return "Drawing the visual…";
  if (card.work.kind === "questions") return "Preparing questions…";
  if ((card.answers?.length ?? 0) > 0) return "Drafting from your answers + sources…";
  return card.mode === "interview" ? "Drafting from recent sources…" : "Drafting…";
}

/** Work that has waited over three minutes with no pipeline run going: say so and offer to start one. */
export function StillWaiting({ card, className }: { card: Card; className?: string }) {
  const run = useDesk((s) => s.run);
  const dispatch = useDesk((s) => s.dispatchNow);
  const github = useDesk((s) => s.connection?.mode === "github");
  const now = useNow(20_000);
  const since = card.work?.requested_at ? new Date(card.work.requested_at).getTime() : NaN;
  const busy = run.state === "queued" || run.state === "running";
  if (!github || !card.work || Number.isNaN(since) || busy || now.getTime() - since < 3 * 60_000) return null;
  return (
    <span className={cx("text-[12.5px] text-muted", className)}>
      Still waiting ·{" "}
      <button
        type="button"
        className="font-medium text-accent hover:underline"
        onClick={(e) => {
          e.stopPropagation();
          void dispatch();
        }}
      >
        Run now
      </button>
    </span>
  );
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
    { show: !!f.ai_tells?.length, icon: <Bot className="size-3.5" />, label: tellSummary(f.ai_tells ?? []), tone: "text-warn" },
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

export function SkipMenu({ card, size = "sm", side = "bottom" }: { card: Card; size?: "sm" | "md"; side?: "top" | "bottom" }) {
  const act = useDesk((s) => s.act);
  const toast = useDesk((s) => s.toast);
  const askWhy = useDesk((s) => s.askSkipReason);
  const skip = (r: (typeof MENU_SKIP_REASONS)[number]) => {
    // "Other" says nothing without the reason, so it asks first; the rest skip in one tap and can add a reason.
    if (r.needsNote) return askWhy(card.id, r.value);
    act({ type: "card.skip", card_id: card.id, reason: r.value });
    toast("ok", `Skipped. ${r.learns}`, { label: "Add why", onAction: () => askWhy(card.id, r.value) });
  };
  // Right topic, wrong platform: a version for the other one is drafted and this card is skipped.
  const other = card.platform === "linkedin" ? "x" : "linkedin";
  const move = () =>
    act(
      { type: "card.crosspost", card_id: card.id, target_platform: other, mode: "switch", note: "" },
      { toast: `Moving it to ${PLATFORM_LABEL[other]}: the new card appears within 1–3 minutes. The topic counts as a good pick, only the platform as wrong.` },
    );
  return (
    <Menu
      label="Skip reasons"
      side={side}
      trigger={(p) => (
        <Button size={size} variant="ghost" {...p} onClick={(e) => { e.stopPropagation(); p.onClick(); }}>
          Skip
        </Button>
      )}
      items={[
        ...MENU_SKIP_REASONS.map((r) => ({ label: r.needsNote ? `${r.label}…` : r.label, hint: r.help, onSelect: () => skip(r) })),
        { label: `Move to ${PLATFORM_LABEL[other]} instead`, hint: "Right topic, wrong platform", onSelect: move },
      ]}
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
  // Drafted from sources, with questions he may answer to make it his own.
  const optional = card.status !== "needs_input" && card.mode === "interview" && !card.answers?.length ? card.questions?.length ?? 0 : 0;
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
        {card.kind && card.kind !== "news" && (
          <Badge tone="info" title={card.crosspost_of ? "Made from a card for the other platform" : undefined}>
            {card.kind === "adapt" ? (card.crosspost_of ? "Cross-post" : "Adapted") : card.kind[0].toUpperCase() + card.kind.slice(1)}
          </Badge>
        )}
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
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-accent">
            <Loader2 className="size-4 animate-spin" /> {work}
            <StillWaiting card={card} />
          </span>
        ) : questions ? (
          <span className="flex items-start gap-2 text-warn">
            <MessageCircleQuestion className="mt-0.5 size-4 shrink-0" />
            <span>
              {questions} optional question{questions === 1 ? "" : "s"}: <span className="text-text">{card.questions?.[0]?.q}</span>
            </span>
          </span>
        ) : brief ? (
          <span className="text-muted">Draft skipped (model quota). Open it and tap <b>Draft this</b>, or write it yourself from the angle: {card.angle}</span>
        ) : (
          <p className="line-clamp-3 whitespace-pre-line">{text || card.angle}</p>
        )}
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2" onClick={(e) => e.stopPropagation()}>
        <span className="flex min-w-0 items-center gap-1.5 truncate text-[12px] text-faint">
          {optional > 0 && (
            <Badge tone="info" icon={<MessageCircleQuestion className="size-3" />} title="Answer them to add your own experience; the draft works without them">
              {optional} optional question{optional === 1 ? "" : "s"}
            </Badge>
          )}
          <span className="truncate">{card.angle && !brief ? `Angle: ${card.angle}` : ""}</span>
        </span>
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
