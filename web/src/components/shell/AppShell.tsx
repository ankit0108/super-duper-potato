import { useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  BarChart3,
  Cloud,
  CloudOff,
  History,
  LayoutGrid,
  Loader2,
  MoreHorizontal,
  RefreshCw,
  Rss,
  Scale,
  Search,
  Settings,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { Link, useRoute } from "@/lib/router";
import { relative } from "@/lib/time";
import { useDesk } from "@/state/store";
import { useNow, useToday, useTz } from "@/state/hooks";
import { localDateKey } from "@/lib/time";
import { cx } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Banners } from "./Banners";

type NavItem = { to: string; label: string; icon: ReactNode; match: (p: string) => boolean; count?: number; mobile?: boolean };

function useNavItems(): NavItem[] {
  const view = useDesk((s) => s.view);
  const today = useToday();
  const tz = useTz();
  return useMemo(() => {
    const cards = view?.cards ?? [];
    const needs = cards.filter((c) => c.status === "needs_input" || c.status === "blocked").length;
    const todays = cards.filter((c) => c.status === "suggested" && localDateKey(c.delivered_at ?? c.created_at, tz) === today).length;
    const review = (view?.metrics ?? []).filter((m) => m.status === "needs_review").length;
    const proposals = (view?.proposals ?? []).filter((p) => p.status === "pending").length;
    const errors = (view?.warnings ?? []).filter((w) => w.level === "error").length;
    return [
      { to: "/", label: "Board", icon: <LayoutGrid className="size-5" />, match: (p) => p === "/" || p.startsWith("/card"), count: needs + todays, mobile: true },
      { to: "/requests", label: "Requests", icon: <Search className="size-5" />, match: (p) => p.startsWith("/requests"), mobile: true },
      { to: "/metrics", label: "Metrics", icon: <BarChart3 className="size-5" />, match: (p) => p.startsWith("/metrics"), count: review, mobile: true },
      { to: "/insights", label: "Insights", icon: <Sparkles className="size-5" />, match: (p) => p.startsWith("/insights"), count: proposals, mobile: true },
      { to: "/stances", label: "Stances", icon: <Scale className="size-5" />, match: (p) => p.startsWith("/stances") },
      { to: "/sources", label: "Sources", icon: <Rss className="size-5" />, match: (p) => p.startsWith("/sources") },
      { to: "/history", label: "History", icon: <History className="size-5" />, match: (p) => p.startsWith("/history") },
      { to: "/system", label: "System", icon: <Activity className="size-5" />, match: (p) => p.startsWith("/system"), count: errors },
      { to: "/settings", label: "Settings", icon: <Settings className="size-5" />, match: (p) => p.startsWith("/settings") },
    ];
  }, [view, today, tz]);
}

export function SyncStatus({ compact }: { compact?: boolean }) {
  const outbox = useDesk((s) => s.outbox);
  const online = useDesk((s) => s.online);
  const fetchedAt = useDesk((s) => s.fetchedAt);
  const loading = useDesk((s) => s.loading);
  const run = useDesk((s) => s.run);
  const refresh = useDesk((s) => s.refresh);
  const retry = useDesk((s) => s.retryFailed);
  const mode = useDesk((s) => s.connection?.mode);
  const now = useNow(20_000);
  const unsent = outbox.filter((i) => i.state === "pending" || i.state === "sending").length;
  const failed = outbox.filter((i) => i.state === "failed").length;
  const waiting = outbox.filter((i) => i.state === "sent").length;

  let icon = <Cloud className="size-4" aria-hidden />;
  let text = fetchedAt ? `Synced ${relative(fetchedAt, now)}` : "Not synced yet";
  let tone = "text-muted";
  if (mode === "demo") text = "Demo mode";
  if (!online) {
    icon = <CloudOff className="size-4" aria-hidden />;
    text = unsent ? `Offline · ${unsent} change${unsent === 1 ? "" : "s"} saved here` : "Offline";
    tone = "text-warn";
  } else if (failed) {
    icon = <TriangleAlert className="size-4" aria-hidden />;
    text = `${failed} change${failed === 1 ? "" : "s"} not saved`;
    tone = "text-bad";
  } else if (unsent) {
    icon = <Loader2 className="size-4 animate-spin" aria-hidden />;
    text = `Saving ${unsent}…`;
  } else if (run.state === "queued" || run.state === "running") {
    icon = <Loader2 className="size-4 animate-spin" aria-hidden />;
    text = run.state === "queued" ? "Pipeline starting…" : "Pipeline working…";
    tone = "text-accent";
  } else if (waiting && !compact) {
    text = `${text} · ${waiting} waiting for the next run`;
  }
  return (
    <div className="flex items-center gap-1">
      <span className={cx("inline-flex items-center gap-1.5 text-[13px]", tone)} role="status" aria-live="polite">
        {icon}
        <span className={compact ? "sr-only sm:not-sr-only" : ""}>{text}</span>
      </span>
      {failed > 0 && (
        <button type="button" onClick={retry} className="ml-1 text-[13px] font-medium text-accent hover:underline">
          Retry
        </button>
      )}
      {run.url && (run.state === "running" || run.state === "queued") && (
        <a href={run.url} target="_blank" rel="noreferrer" className="ml-1 text-[13px] text-accent hover:underline">
          View run
        </a>
      )}
      <button
        type="button"
        onClick={() => void refresh()}
        aria-label="Refresh"
        title="Refresh"
        className="ml-1 rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text"
      >
        <RefreshCw className={cx("size-4", loading && "animate-spin")} />
      </button>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const route = useRoute();
  const items = useNavItems();
  const [more, setMore] = useState(false);
  const name = useDesk((s) => s.view?.meta?.display_name ?? "");
  const mobileItems = items.filter((i) => i.mobile);
  const moreActive = !mobileItems.some((i) => i.match(route.path));

  return (
    <div className="flex min-h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-border bg-surface/60 px-3 py-4 lg:flex">
        <div className="mb-5 flex items-center gap-2 px-2">
          <img src="./icon.svg" alt="" className="size-7 rounded-lg" />
          <div className="leading-tight">
            <div className="text-sm font-semibold">PBS Desk</div>
            {name && <div className="text-xs text-muted">{name}'s personal brand</div>}
          </div>
        </div>
        <nav aria-label="Main" className="flex flex-1 flex-col gap-0.5">
          {items.map((it) => {
            const active = it.match(route.path);
            return (
              <Link
                key={it.to}
                to={it.to}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                  active ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2 hover:text-text",
                )}
              >
                {it.icon}
                <span className="flex-1">{it.label}</span>
                {!!it.count && <span className="rounded-full bg-accent px-1.5 text-[11px] font-semibold tabular-nums text-accent-fg">{it.count}</span>}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border px-1 pt-3">
          <SyncStatus />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-border bg-bg/90 px-4 py-2.5 backdrop-blur lg:hidden">
          <div className="flex items-center gap-2">
            <img src="./icon.svg" alt="" className="size-6 rounded-md" />
            <span className="text-sm font-semibold">PBS Desk</span>
          </div>
          <SyncStatus compact />
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 pt-4 pb-28 lg:px-8 lg:pt-6 lg:pb-10">
          <Banners />
          {children}
        </main>
      </div>

      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-border bg-surface/95 backdrop-blur safe-bottom lg:hidden">
        {mobileItems.map((it) => {
          const active = it.match(route.path);
          return (
            <Link key={it.to} to={it.to} aria-current={active ? "page" : undefined} className={cx("relative flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium", active ? "text-accent" : "text-muted")}>
              {it.icon}
              {it.label}
              {!!it.count && <span className="absolute top-1 left-1/2 ml-2 rounded-full bg-accent px-1 text-[10px] font-semibold text-accent-fg">{it.count}</span>}
            </Link>
          );
        })}
        <button type="button" onClick={() => setMore(true)} className={cx("flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium", moreActive ? "text-accent" : "text-muted")}>
          <MoreHorizontal className="size-5" />
          More
        </button>
      </nav>

      <Dialog open={more} onClose={() => setMore(false)} title="More">
        <div className="grid grid-cols-2 gap-2">
          {items
            .filter((i) => !i.mobile)
            .map((it) => (
              <Link key={it.to} to={it.to} onClick={() => setMore(false)} className="flex items-center gap-2.5 rounded-xl border border-border px-3 py-3 text-sm font-medium hover:bg-surface-2">
                {it.icon}
                {it.label}
                {!!it.count && <span className="ml-auto rounded-full bg-accent px-1.5 text-[11px] text-accent-fg">{it.count}</span>}
              </Link>
            ))}
        </div>
      </Dialog>
    </div>
  );
}
