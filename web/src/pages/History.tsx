import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { Card, Platform } from "@/types";
import { FORMAT_LABEL, STATUS_LABEL, pct } from "@/lib/format";
import { Link } from "@/lib/router";
import { formatDate } from "@/lib/time";
import { useDesk } from "@/state/store";
import { usePillarLabels, useTz } from "@/state/hooks";
import { Badge, PlatformMark, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Empty } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Field";

export function History() {
  const view = useDesk((s) => s.view);
  const loadArchive = useDesk((s) => s.loadArchive);
  const toast = useDesk((s) => s.toast);
  const demo = useDesk((s) => s.connection?.mode === "demo");
  const tz = useTz();
  const pillar = usePillarLabels();
  const [q, setQ] = useState("");
  const [platform, setPlatform] = useState<"" | Platform>("");
  const [status, setStatus] = useState("");
  const [archive, setArchive] = useState<Card[]>([]);
  const [loadedMonths, setLoadedMonths] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const posts = new Map((view?.posts ?? []).map((p) => [p.card_id, p]));
  const all = useMemo(() => {
    const byId = new Map<string, Card>();
    for (const c of [...archive, ...(view?.cards ?? [])]) byId.set(c.id, c);
    return [...byId.values()].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
  }, [archive, view?.cards]);
  const needle = q.trim().toLowerCase();
  const rows = all.filter(
    (c) =>
      (!platform || c.platform === platform) &&
      (!status || c.status === status) &&
      (!needle || [c.title, c.angle, c.draft?.text, ...(c.draft?.posts ?? [])].some((t) => t?.toLowerCase().includes(needle))),
  );
  const months = (view?.archive_months ?? []).filter((m) => !loadedMonths.includes(m));
  const loadMore = async () => {
    const next = months[0];
    if (!next) return;
    setLoading(true);
    try {
      const cards = await loadArchive(next);
      setArchive((a) => [...a, ...cards]);
      setLoadedMonths((m) => [...m, next]);
    } catch (e) {
      toast("bad", `Couldn't load ${next}: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">History</h1>
        <p className="mt-1 text-sm text-muted">Every card from the last week is here; load older months from your data repo.</p>
      </header>
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-60 flex-1">
          <Search className="pointer-events-none absolute top-3 left-3 size-4 text-faint" />
          <Input aria-label="Search cards" placeholder="Search titles, angles and drafts" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
        </div>
        <Select aria-label="Platform" value={platform} onChange={(e) => setPlatform(e.target.value as "" | Platform)} className="w-36">
          <option value="">All platforms</option>
          <option value="linkedin">LinkedIn</option>
          <option value="x">X</option>
        </Select>
        <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-40">
          <option value="">Any status</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
      </div>
      {rows.length === 0 ? (
        <Empty title="Nothing matches">Try a different search or filter.</Empty>
      ) : (
        <ul className="divide-y divide-border rounded-2xl border border-border bg-surface">
          {rows.slice(0, 300).map((c) => {
            const post = posts.get(c.id);
            return (
              <li key={c.id}>
                <Link to={`/card/${c.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 hover:bg-surface-2">
                  <PlatformMark platform={c.platform} className="size-4 text-[9px]" />
                  <span className="min-w-0 flex-1 truncate text-[13.5px]">{c.title}</span>
                  <span className="text-[12px] text-muted">
                    {pillar(c.platform, c.pillar)} · {FORMAT_LABEL[c.format]}
                  </span>
                  {post?.edit_ratio != null && <Badge tone="neutral">edit {pct(post.edit_ratio)}</Badge>}
                  <StatusBadge status={c.status} />
                  <span className="w-24 text-right text-[12px] text-muted">{formatDate(c.created_at, tz)}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {months.length > 0 && !demo && (
        <div className="flex justify-center">
          <Button onClick={() => void loadMore()} loading={loading}>
            Load {months[0]}
          </Button>
        </div>
      )}
    </div>
  );
}
