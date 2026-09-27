import { useEffect, useMemo, type ReactNode } from "react";
import { CalendarClock, CheckCircle2, Inbox, Sparkles } from "lucide-react";
import type { Card, Platform } from "@/types";
import { useDesk } from "@/state/store";
import { useNow, useToday, useTz } from "@/state/hooks";
import { boardSections } from "@/state/selectors";
import { formatTime, greeting, localDateKey } from "@/lib/time";
import { FORMAT_LABEL, SKIP_REASONS } from "@/lib/format";
import { Link } from "@/lib/router";
import { CardTile } from "@/components/card/CardTile";
import { Badge, PlatformMark } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Empty, Skeleton } from "@/components/ui/Feedback";
import { Segmented } from "@/components/ui/Tabs";

function Section({ title, hint, count, children, id }: { title: string; hint?: ReactNode; count?: number; children: ReactNode; id: string }) {
  return (
    <section aria-labelledby={id} className="mt-7 first:mt-0">
      <div className="mb-2.5 flex items-baseline justify-between gap-3">
        <h2 id={id} className="text-[15px] font-semibold">
          {title} {count != null && <span className="font-normal text-muted tabular-nums">· {count}</span>}
        </h2>
        {hint && <span className="text-[12.5px] text-muted">{hint}</span>}
      </div>
      {children}
    </section>
  );
}

function useBoardKeys() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable], dialog")) return;
      if (e.key !== "j" && e.key !== "k") return;
      const tiles = Array.from(document.querySelectorAll<HTMLElement>("[data-tile]"));
      if (!tiles.length) return;
      const i = tiles.indexOf(document.activeElement as HTMLElement);
      const next = e.key === "j" ? Math.min(tiles.length - 1, i + 1) : Math.max(0, i - 1);
      tiles[i < 0 ? 0 : next]?.focus();
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

export function Board() {
  const view = useDesk((s) => s.view);
  const pending = useDesk((s) => s.pending);
  const prefs = useDesk((s) => s.prefs);
  const setPrefs = useDesk((s) => s.setPrefs);
  const loading = useDesk((s) => s.loading);
  const tz = useTz();
  const today = useToday();
  const now = useNow(60_000);
  useBoardKeys();
  const sections = useMemo(() => boardSections(view, today, tz, prefs.platform), [view, today, tz, prefs.platform]);

  if (!view) {
    return loading ? (
      <div className="space-y-3">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-3 md:grid-cols-2">
          <Skeleton className="h-44" />
          <Skeleton className="h-44" />
        </div>
      </div>
    ) : (
      <Empty icon={<Inbox className="size-8" />} title="No desk yet" action={<Link to="/system" className="text-accent hover:underline">Open System</Link>}>
        The first pipeline run creates your desk. Start one from System, or wait for the morning schedule.
      </Empty>
    );
  }

  const delivery = view.delivery;
  const deliveredToday = delivery && delivery.local_date === today;
  const name = view.meta?.display_name ?? "";
  const next = view.meta?.next_delivery_local;
  const renderTiles = (cards: Card[]) => (
    <div className="grid gap-3 md:grid-cols-2">
      {cards.map((c) => (
        <CardTile key={c.id} card={c} pending={pending.cards.has(c.id)} />
      ))}
    </div>
  );
  const platforms: Platform[] = prefs.platform === "all" ? ["linkedin", "x"] : [prefs.platform];
  const todayCount = sections.today.linkedin.length + sections.today.x.length;

  return (
    <div>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[13px] text-muted">{new Intl.DateTimeFormat("en-AU", { timeZone: tz, weekday: "long", day: "numeric", month: "long" }).format(now)}</p>
          <h1 className="mt-0.5 text-2xl font-semibold tracking-tight">
            {greeting(tz, now)}
            {name ? `, ${name}` : ""}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-muted">
            <CalendarClock className="size-4" aria-hidden />
            {deliveredToday ? (
              <>
                Delivered {formatTime(delivery.delivered_at, tz)} · {delivery.counts?.linkedin ?? 0} LinkedIn · {delivery.counts?.x ?? 0} X
                {delivery.degraded && <Badge tone="warn">Some drafts skipped (free-tier limits)</Badge>}
              </>
            ) : next ? (
              <>Next delivery around {formatTime(new Date(next), tz)}{localDateKey(new Date(next), tz) !== today ? " tomorrow" : ""}</>
            ) : (
              "No delivery yet today"
            )}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2 text-[13px]" aria-label="Posted today">
            {(["linkedin", "x"] as const).map((p) => (
              <span key={p} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2 py-1">
                <PlatformMark platform={p} className="size-4 text-[9px]" />
                {sections.postedToday[p] > 0 ? (
                  <span className="inline-flex items-center gap-1 text-ok">
                    <CheckCircle2 className="size-3.5" /> Posted
                  </span>
                ) : (
                  <span className="text-muted">Not yet</span>
                )}
              </span>
            ))}
          </div>
          <Segmented
            label="Platform"
            value={prefs.platform}
            onChange={(v) => setPrefs({ platform: v })}
            items={[
              { value: "all", label: "All", count: sections.counts.all },
              { value: "linkedin", label: "LinkedIn", count: sections.counts.linkedin },
              { value: "x", label: "X", count: sections.counts.x },
            ]}
          />
        </div>
      </header>

      {sections.needsYou.length > 0 && (
        <Section id="sec-needs" title="Needs you" count={sections.needsYou.length} hint="Blocked or failed drafts from earlier days">
          {renderTiles(sections.needsYou)}
        </Section>
      )}

      <Section id="sec-today" title="Today's picks" count={todayCount} hint="Ranked best first · press j / k to move, Enter to open">
        {todayCount === 0 ? (
          <Empty icon={<Sparkles className="size-7" />} title={deliveredToday ? "All of today's picks are handled" : "Today's picks haven't arrived yet"}>
            {deliveredToday ? "Nice. Anything else still open is under This week." : "They arrive by about 6am. You can also ask for any topic on the Requests page."}
          </Empty>
        ) : (
          <div className={platforms.length > 1 ? "grid gap-6 xl:grid-cols-2" : ""}>
            {platforms.map((p) => (
              <div key={p}>
                {platforms.length > 1 && (
                  <h3 className="mb-2 flex items-center gap-2 text-[13px] font-semibold text-muted">
                    <PlatformMark platform={p} className="size-4 text-[9px]" /> {p === "linkedin" ? "LinkedIn" : "X"} · {sections.today[p].length}
                  </h3>
                )}
                <div className="grid gap-3">{sections.today[p].map((c) => <CardTile key={c.id} card={c} pending={pending.cards.has(c.id)} />)}</div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {sections.inProgress.length > 0 && (
        <Section id="sec-progress" title="In progress" count={sections.inProgress.length} hint="Editing cards stay for 72 hours after your last change">
          {renderTiles(sections.inProgress)}
        </Section>
      )}

      {sections.thisWeek.length > 0 && (
        <Section id="sec-week" title="This week" count={sections.thisWeek.length} hint="Interview questions, evergreen and request cards stay for a few days">
          {renderTiles(sections.thisWeek)}
        </Section>
      )}

      {sections.doneToday.length > 0 && (
        <Section id="sec-done" title="Done today" count={sections.doneToday.length}>
          <ul className="divide-y divide-border rounded-2xl border border-border bg-surface">
            {sections.doneToday.map((c) => (
              <li key={c.id}>
                <Link to={`/card/${c.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-2">
                  <PlatformMark platform={c.platform} className="size-4 text-[9px]" />
                  <span className="min-w-0 flex-1 truncate text-sm">{c.title}</span>
                  <span className="text-[12px] text-muted">{FORMAT_LABEL[c.format]}</span>
                  {c.status === "posted" ? <Badge tone="ok">Posted</Badge> : <Badge tone="neutral">{SKIP_REASONS.find((r) => r.value === c.skip?.reason)?.label ?? "Skipped"}</Badge>}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <div className="mt-8 flex justify-center">
        <Link to="/requests">
          <Button variant="ghost" size="sm">
            Want something specific? Ask for any topic →
          </Button>
        </Link>
      </div>
    </div>
  );
}
