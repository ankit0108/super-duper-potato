import type { ReactNode } from "react";
import type { CardStatus, Platform } from "@/types";
import { STATUS_LABEL } from "@/lib/format";
import { cx } from "./Button";

export type Tone = "neutral" | "accent" | "ok" | "warn" | "bad" | "info" | "edit" | "linkedin" | "x";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted border-border",
  accent: "bg-accent-soft text-accent border-transparent",
  ok: "bg-ok-soft text-ok border-transparent",
  warn: "bg-warn-soft text-warn border-transparent",
  bad: "bg-bad-soft text-bad border-transparent",
  info: "bg-info-soft text-info border-transparent",
  edit: "bg-edit-soft text-edit border-transparent",
  linkedin: "bg-linkedin/10 text-linkedin border-transparent",
  x: "bg-x/10 text-x border-transparent",
};

export function Badge({ tone = "neutral", children, className, icon, title }: { tone?: Tone; children: ReactNode; className?: string; icon?: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11.5px] font-medium leading-4 whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

const statusTone: Record<CardStatus, Tone> = {
  drafting: "info",
  suggested: "accent",
  needs_input: "warn",
  editing: "edit",
  posted: "ok",
  skipped: "neutral",
  expired: "neutral",
  blocked: "bad",
  failed: "bad",
};

export function StatusBadge({ status }: { status: CardStatus }) {
  return <Badge tone={statusTone[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function PlatformMark({ platform, className }: { platform: Platform; className?: string }) {
  if (platform === "linkedin") {
    return (
      <span className={cx("inline-flex size-5 items-center justify-center rounded bg-linkedin text-[11px] font-bold text-white", className)} aria-label="LinkedIn" role="img">
        in
      </span>
    );
  }
  return (
    <span className={cx("inline-flex size-5 items-center justify-center rounded bg-x text-[11px] font-bold text-bg", className)} aria-label="X" role="img">
      𝕏
    </span>
  );
}
