import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2, OctagonAlert, X } from "lucide-react";
import { useDesk, type ToastTone } from "@/state/store";
import { cx } from "./Button";

const bannerTone: Record<ToastTone, string> = {
  info: "border-info/25 bg-info-soft text-info",
  ok: "border-ok/25 bg-ok-soft text-ok",
  warn: "border-warn/25 bg-warn-soft text-warn",
  bad: "border-bad/25 bg-bad-soft text-bad",
};
const icons: Record<ToastTone, ReactNode> = {
  info: <Info className="size-4 shrink-0" aria-hidden />,
  ok: <CheckCircle2 className="size-4 shrink-0" aria-hidden />,
  warn: <AlertTriangle className="size-4 shrink-0" aria-hidden />,
  bad: <OctagonAlert className="size-4 shrink-0" aria-hidden />,
};

export function Banner({ tone = "info", children, action, onDismiss }: { tone?: ToastTone; children: ReactNode; action?: ReactNode; onDismiss?: () => void }) {
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={cx("flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm", bannerTone[tone])}>
      <span className="mt-0.5">{icons[tone]}</span>
      <div className="min-w-0 flex-1 text-text">{children}</div>
      {action}
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Dismiss" className="rounded p-0.5 text-muted hover:text-text">
          <X className="size-4" />
        </button>
      )}
    </div>
  );
}

export function Toasts() {
  const toasts = useDesk((s) => s.toasts);
  const dismiss = useDesk((s) => s.dismissToast);
  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex flex-col items-center gap-2 px-4 lg:bottom-6">
      {toasts.map((t) => (
        <div key={t.id} className={cx("pointer-events-auto flex w-full max-w-md items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm shadow-lg backdrop-blur", bannerTone[t.tone], "bg-surface/95")}>
          {icons[t.tone]}
          <span className="flex-1 text-text">{t.text}</span>
          {t.actionLabel && (
            <button
              type="button"
              className="font-semibold text-accent hover:underline"
              onClick={() => {
                t.onAction?.();
                dismiss(t.id);
              }}
            >
              {t.actionLabel}
            </button>
          )}
          <button type="button" onClick={() => dismiss(t.id)} aria-label="Dismiss" className="text-muted hover:text-text">
            <X className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-border-strong px-6 py-10 text-center">
      {icon && <div className="mb-3 text-faint">{icon}</div>}
      <h3 className="font-semibold">{title}</h3>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-lg bg-surface-3", className)} aria-hidden />;
}

export function Panel({ title, description, actions, children, className }: { title?: ReactNode; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-2xl border border-border bg-surface", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-2 border-b border-border px-4 py-3">
          <div>
            {title && <h2 className="text-[15px] font-semibold">{title}</h2>}
            {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-muted">{children}</kbd>;
}
