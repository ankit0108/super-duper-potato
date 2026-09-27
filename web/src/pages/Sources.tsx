import { useMemo, useState } from "react";
import { ExternalLink, Pause, Play, Plus, Replace, Trash2 } from "lucide-react";
import type { Source } from "@/types";
import { safeUrl } from "@/lib/compose";
import { pct } from "@/lib/format";
import { relative } from "@/lib/time";
import { useDesk } from "@/state/store";
import { useNow } from "@/state/hooks";
import { Badge } from "@/components/ui/Badge";
import { Button, IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Empty } from "@/components/ui/Feedback";
import { Field, Input, Select } from "@/components/ui/Field";
import { Tabs } from "@/components/ui/Tabs";

// Store selectors must return stable references (zustand 5), so fallbacks live outside them.
const NONE: never[] = [];

type Scout = "tech" | "affairs" | "startups" | "life";
const SCOUTS: Array<{ value: Scout; label: string }> = [
  { value: "tech", label: "Tech & AI" },
  { value: "affairs", label: "Affairs" },
  { value: "startups", label: "Startups" },
  { value: "life", label: "Life" },
];
const KIND_LABEL: Record<string, string> = {
  rss: "RSS",
  gnews: "Google News",
  arxiv: "arXiv",
  hf_papers: "HF papers",
  hn_front: "Hacker News",
  hn_show: "Show HN",
  wikipedia_otd: "Wikipedia",
  reddit: "Reddit",
};

function health(s: Source, now: Date): { tone: "ok" | "warn" | "bad" | "neutral"; text: string } {
  const h = s.health ?? {};
  if (!s.active) return { tone: "neutral", text: s.paused_reason ? "Paused automatically" : "Paused" };
  if (!h.last_fetch_at) return { tone: "neutral", text: "Not fetched yet" };
  if ((h.consecutive_failures ?? 0) >= 3) return { tone: "bad", text: `Failing (${h.consecutive_failures}×)` };
  if ((h.consecutive_failures ?? 0) > 0) return { tone: "warn", text: "Failed last run" };
  return { tone: "ok", text: `OK ${relative(h.last_success_at, now)}` };
}

function AddSourceDialog({ open, onClose, scout, replacing }: { open: boolean; onClose: () => void; scout: Scout; replacing?: Source }) {
  const act = useDesk((s) => s.act);
  const [kind, setKind] = useState<"gnews" | "rss" | "reddit">(replacing ? "gnews" : "rss");
  const [name, setName] = useState(replacing ? `Google News: ${replacing.name}` : "");
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState(replacing ? replacing.name.replace(/\s*\(.*\)$/, "") : "");
  const [tier, setTier] = useState<string>(replacing?.tier ?? "");
  const [lang, setLang] = useState<"en" | "hi">((replacing?.lang as "en" | "hi") ?? "en");
  const valid = name.trim() && (kind === "gnews" ? query.trim() : !!safeUrl(url));
  const save = () => {
    const id = `user-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40)}`;
    const events = [
      {
        type: "source.upsert" as const,
        source_id: id,
        name: name.trim(),
        kind,
        scout: (replacing?.scout as Scout) ?? scout,
        lang,
        ...(tier ? { tier: tier as "world" | "india" | "bihar" | "other" } : {}),
        ...(kind === "gnews" ? { query: query.trim() } : { url: url.trim() }),
        active: true,
      },
      ...(replacing ? [{ type: "source.upsert" as const, source_id: replacing.id, active: false }] : []),
    ];
    act(events, { toast: replacing ? "Replaced. The old source is paused." : "Source added. It's fetched on the next run." });
    onClose();
  };
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={replacing ? `Replace ${replacing.name}` : "Add a source"}
      description="Google News queries are the most robust: they survive outlets changing their feed URLs."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save} disabled={!valid}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Type" htmlFor="src-kind">
          <Select id="src-kind" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
            <option value="rss">RSS or Atom feed</option>
            <option value="gnews">Google News search</option>
            <option value="reddit">Reddit feed (best effort)</option>
          </Select>
        </Field>
        <Field label="Name" htmlFor="src-name">
          <Input id="src-name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        {kind === "gnews" ? (
          <Field label="Search query" htmlFor="src-q" hint='Google News syntax works: quotes, OR, and "when:2d" for recency.'>
            <Input id="src-q" value={query} onChange={(e) => setQuery(e.target.value)} placeholder='"Bihar" infrastructure when:2d' />
          </Field>
        ) : (
          <Field label="Feed URL" htmlFor="src-url" error={url && !safeUrl(url) ? "Needs to be an http(s) link." : undefined}>
            <Input id="src-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/feed.xml" />
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Tier (affairs)" htmlFor="src-tier">
            <Select id="src-tier" value={tier} onChange={(e) => setTier(e.target.value)}>
              <option value="">—</option>
              <option value="world">World</option>
              <option value="india">India</option>
              <option value="bihar">Bihar</option>
            </Select>
          </Field>
          <Field label="Language" htmlFor="src-lang">
            <Select id="src-lang" value={lang} onChange={(e) => setLang(e.target.value as "en" | "hi")}>
              <option value="en">English</option>
              <option value="hi">Hindi (translated)</option>
            </Select>
          </Field>
        </div>
      </div>
    </Dialog>
  );
}

export function Sources() {
  const sources = useDesk((s) => s.view?.sources) ?? NONE;
  const pending = useDesk((s) => s.pending.sources);
  const act = useDesk((s) => s.act);
  const now = useNow(60_000);
  const [scout, setScout] = useState<Scout>("tech");
  const [adding, setAdding] = useState(false);
  const [replacing, setReplacing] = useState<Source | undefined>();
  const grouped = useMemo(() => {
    const out: Record<Scout, Source[]> = { tech: [], affairs: [], startups: [], life: [] };
    for (const s of sources) (out[s.scout as Scout] ?? out.tech).push(s);
    for (const k of Object.keys(out) as Scout[]) out[k].sort((a, b) => Number(b.active) - Number(a.active) || a.name.localeCompare(b.name));
    return out;
  }, [sources]);
  const failing = sources.filter((s) => s.active && (s.health?.consecutive_failures ?? 0) >= 3).length;
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sources</h1>
          <p className="mt-1 text-sm text-muted">
            {sources.filter((s) => s.active).length} active sources. {failing ? `${failing} failing: replace them with a Google News query.` : "Failing sources pause themselves after a week."}
          </p>
        </div>
        <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
          Add source
        </Button>
      </header>
      <Tabs label="Scouts" value={scout} onChange={setScout} items={SCOUTS.map((s) => ({ ...s, count: grouped[s.value].length }))} />
      {grouped[scout].length === 0 ? (
        <Empty title="No sources for this scout">{scout === "life" ? "Life posts come from interview questions, not feeds." : "Add a feed or a Google News query."}</Empty>
      ) : (
        <ul className="divide-y divide-border rounded-2xl border border-border bg-surface">
          {grouped[scout].map((s) => {
            const h = health(s, now);
            const link = safeUrl(s.url);
            const y = s.yield_stats as { items_28d?: number; picked_28d?: number; yield?: number | null } | undefined;
            return (
              <li key={s.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-medium">{s.name}</span>
                    <Badge tone="neutral">{KIND_LABEL[s.kind] ?? s.kind}</Badge>
                    {s.tier && <Badge tone="info">{s.tier}</Badge>}
                    {s.lang === "hi" && <Badge tone="info">Hindi</Badge>}
                    {s.added_by === "user" && <Badge tone="accent">Yours</Badge>}
                    {s.best_effort && <Badge tone="neutral">Best effort</Badge>}
                    {pending.has(s.id) && <Badge tone="neutral">Syncing</Badge>}
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-3 text-[12.5px] text-muted">
                    <Badge tone={h.tone}>{h.text}</Badge>
                    {y?.items_28d != null && (
                      <span>
                        {y.items_28d} items · {y.picked_28d ?? 0} picked · yield {pct(y.yield)}
                      </span>
                    )}
                    {s.query && <span className="truncate">“{s.query}”</span>}
                  </div>
                  {(s.paused_reason || s.health?.last_error) && <p className="mt-0.5 text-[12px] text-faint">{s.paused_reason ?? s.health?.last_error}</p>}
                </div>
                <div className="flex items-center">
                  {link && <IconButton size="sm" label="Open feed" icon={<ExternalLink className="size-4" />} onClick={() => window.open(link, "_blank", "noopener")} />}
                  {(s.health?.consecutive_failures ?? 0) >= 1 && s.kind !== "gnews" && <IconButton size="sm" label="Replace with a Google News query" icon={<Replace className="size-4" />} onClick={() => setReplacing(s)} />}
                  <IconButton
                    size="sm"
                    label={s.active ? "Pause" : "Resume"}
                    icon={s.active ? <Pause className="size-4" /> : <Play className="size-4" />}
                    onClick={() => act({ type: "source.upsert", source_id: s.id, active: !s.active })}
                  />
                  <IconButton
                    size="sm"
                    label="Delete"
                    icon={<Trash2 className="size-4" />}
                    onClick={() => {
                      if (window.confirm(`Delete ${s.name}?`)) act({ type: "source.delete", source_id: s.id }, { toast: "Source deleted." });
                    }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <AddSourceDialog key={`add-${adding}`} open={adding} onClose={() => setAdding(false)} scout={scout} />
      <AddSourceDialog key={`rep-${replacing?.id}`} open={!!replacing} onClose={() => setReplacing(undefined)} scout={scout} replacing={replacing} />
    </div>
  );
}
