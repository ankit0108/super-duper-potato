import { useEffect, useMemo, useState } from "react";
import { Check, ImageUp, Loader2, X } from "lucide-react";
import type { Metric, MetricValues, Platform, Post } from "@/types";
import { METRIC_FIELDS, compact, num, pct } from "@/lib/format";
import { compressImage } from "@/lib/image";
import { useRoute, navigate } from "@/lib/router";
import { newId } from "@/lib/storage";
import { formatDate, isoWeek, localDateKey } from "@/lib/time";
import { truncate } from "@/lib/text";
import { useDesk } from "@/state/store";
import { useTz } from "@/state/hooks";
import { Badge, PlatformMark } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Empty, Panel } from "@/components/ui/Feedback";
import { Field, Input, Select } from "@/components/ui/Field";

// Store selectors must return stable references (zustand 5), so fallbacks live outside them.
const NONE: never[] = [];

function MetricsDialog({ post, open, onClose }: { post: Post | undefined; open: boolean; onClose: () => void }) {
  const act = useDesk((s) => s.act);
  const [values, setValues] = useState<Record<string, string>>({});
  useEffect(() => {
    if (open && post) {
      const lm = (post.latest_metrics ?? {}) as Partial<Record<keyof MetricValues, number | null>>;
      setValues(Object.fromEntries(METRIC_FIELDS[post.platform].map((f) => [f.key, lm[f.key] != null ? String(lm[f.key]) : ""])));
    }
  }, [open, post]);
  if (!post) return null;
  const save = () => {
    const out: MetricValues = {};
    for (const f of METRIC_FIELDS[post.platform]) {
      const raw = values[f.key]?.trim();
      if (raw) (out as Record<string, number>)[f.key] = Math.max(0, Math.round(Number(raw.replace(/,/g, ""))));
    }
    if (!Object.keys(out).length) return;
    act({ type: "post.metrics", post_id: post.id, values: out }, { toast: "Numbers saved. Rewards update on the next run." });
    onClose();
  };
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add numbers"
      description={truncate(post.final_text, 120)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save}>
            Save
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        {METRIC_FIELDS[post.platform].map((f) => (
          <Field key={f.key} label={f.label} htmlFor={`m-${f.key}`}>
            <Input
              id={`m-${f.key}`}
              inputMode="numeric"
              value={values[f.key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value.replace(/[^\d,]/g, "") }))}
            />
          </Field>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted">Leave blank what you don't see. Rewards compare each post with your own recent median.</p>
    </Dialog>
  );
}

function CheckIn() {
  const act = useDesk((s) => s.act);
  const stats = useDesk((s) => s.view?.account_stats) ?? NONE;
  const tz = useTz();
  const today = localDateKey(new Date(), tz);
  const latest = (p: Platform) => stats.find((s) => s.platform === p && s.followers != null);
  const [li, setLi] = useState("");
  const [views, setViews] = useState("");
  const [x, setX] = useState("");
  const save = () => {
    const events = [];
    if (li.trim()) events.push({ type: "account.stats" as const, date: today, platform: "linkedin" as const, followers: Number(li.replace(/,/g, "")), profile_views: views.trim() ? Number(views.replace(/,/g, "")) : null });
    if (x.trim()) events.push({ type: "account.stats" as const, date: today, platform: "x" as const, followers: Number(x.replace(/,/g, "")) });
    if (!events.length) return;
    act(events, { toast: "Check-in saved." });
    setLi("");
    setViews("");
    setX("");
  };
  return (
    <Panel title="Weekly check-in" description="Followers once a week is enough. It drives the growth charts and the X reply-angle threshold.">
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="LinkedIn followers" htmlFor="ci-li" hint={latest("linkedin") ? `Last: ${num(latest("linkedin")!.followers)} (${formatDate(latest("linkedin")!.date, tz)})` : "Baseline ~3,100"}>
          <Input id="ci-li" inputMode="numeric" value={li} onChange={(e) => setLi(e.target.value)} />
        </Field>
        <Field label="LinkedIn profile views (week)" htmlFor="ci-views">
          <Input id="ci-views" inputMode="numeric" value={views} onChange={(e) => setViews(e.target.value)} />
        </Field>
        <Field label="X followers" htmlFor="ci-x" hint={latest("x") ? `Last: ${num(latest("x")!.followers)}` : "Baseline ~12"}>
          <Input id="ci-x" inputMode="numeric" value={x} onChange={(e) => setX(e.target.value)} />
        </Field>
      </div>
      <div className="mt-4 flex justify-end">
        <Button variant="primary" onClick={save} disabled={!li.trim() && !x.trim()}>
          Save check-in
        </Button>
      </div>
    </Panel>
  );
}

function Uploads() {
  const act = useDesk((s) => s.act);
  const upload = useDesk((s) => s.uploadBlob);
  const toast = useDesk((s) => s.toast);
  const mode = useDesk((s) => s.connection?.mode);
  const uploads = useDesk((s) => s.view?.uploads) ?? NONE;
  const tz = useTz();
  const [files, setFiles] = useState<File[]>([]);
  const [week, setWeek] = useState(isoWeek(new Date()));
  const [busy, setBusy] = useState(false);
  const send = async () => {
    if (!files.length) return;
    setBusy(true);
    const uploadId = newId("upl");
    const paths: string[] = [];
    try {
      for (let i = 0; i < files.length; i++) {
        const bytes = await compressImage(files[i]);
        const path = `inbox/blobs/${uploadId}_${i + 1}.jpg`;
        await upload(path, bytes);
        paths.push(path);
      }
      act({ type: "metrics.upload", upload_id: uploadId, paths, week, note: null }, { toast: mode === "demo" ? "Demo: upload simulated." : "Uploaded. Numbers appear after the next run; low-confidence ones wait for your check." });
      setFiles([]);
    } catch (e) {
      toast("bad", `Upload failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Analytics screenshots" description="LinkedIn post analytics, X post views, or your follower pages. The model reads the numbers and matches them to posts.">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-border-strong px-4 py-3 text-sm hover:bg-surface-2">
          <ImageUp className="size-5 text-muted" />
          <span>{files.length ? `${files.length} screenshot${files.length === 1 ? "" : "s"} selected` : "Choose screenshots"}</span>
          <input type="file" accept="image/*" multiple className="sr-only" onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 20))} />
        </label>
        <Field label="Week" htmlFor="up-week">
          <Input id="up-week" value={week} onChange={(e) => setWeek(e.target.value)} className="w-32" />
        </Field>
        <Button variant="primary" onClick={() => void send()} loading={busy} disabled={!files.length}>
          Upload
        </Button>
      </div>
      {uploads.length > 0 && (
        <ul className="mt-4 divide-y divide-border text-[13px]">
          {uploads.slice(0, 6).map((u) => (
            <li key={u.id} className="flex items-center justify-between gap-2 py-2">
              <span>
                {u.week ?? "–"} · {u.paths?.length ?? 0} file(s) · {formatDate(u.created_at, tz)}
              </span>
              {u.status === "pending" ? (
                <Badge tone="info" icon={<Loader2 className="size-3 animate-spin" />}>
                  Waiting for the next run
                </Badge>
              ) : u.status === "processed" ? (
                <Badge tone="ok">Processed</Badge>
              ) : (
                <Badge tone="bad">{u.error ?? "Failed"}</Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function ReviewQueue({ posts }: { posts: Post[] }) {
  const act = useDesk((s) => s.act);
  const metrics = useDesk((s) => s.view?.metrics);
  const queue = useMemo(() => (metrics ?? []).filter((m) => m.status === "needs_review"), [metrics]);
  const [choice, setChoice] = useState<Record<string, string>>({});
  if (!queue.length) return null;
  const decide = (m: Metric, action: "confirm" | "reject") => {
    const postId = choice[m.id] ?? m.post_id ?? "";
    act({ type: "metrics.review", metric_id: m.id, action, ...(action === "confirm" && postId ? { post_id: postId } : {}) }, { toast: action === "confirm" ? "Confirmed." : "Discarded." });
  };
  return (
    <Panel title={`Check ${queue.length} extracted number${queue.length === 1 ? "" : "s"}`} description="The model wasn't sure which post these belong to. Pick the post and confirm.">
      <ul className="space-y-3">
        {queue.map((m) => {
          const fields = METRIC_FIELDS[(m.platform as Platform) ?? "linkedin"].filter((f) => m[f.key] != null);
          const snippet = (m.raw as { text_snippet?: string } | undefined)?.text_snippet;
          return (
            <li key={m.id} className="rounded-xl border border-border p-3">
              {snippet && <p className="text-[13px] text-muted">Screenshot text: “{snippet}”</p>}
              <p className="mt-1 text-[13px]">{fields.map((f) => `${f.label}: ${num(m[f.key] as number)}`).join(" · ")}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Select aria-label="Which post" value={choice[m.id] ?? m.post_id ?? ""} onChange={(e) => setChoice((c) => ({ ...c, [m.id]: e.target.value }))} className="h-9 max-w-md flex-1">
                  <option value="">Choose the post…</option>
                  {posts.slice(0, 40).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.platform === "x" ? "X" : "LI"} · {truncate(p.final_text, 70)}
                    </option>
                  ))}
                </Select>
                <Button size="sm" variant="primary" icon={<Check className="size-4" />} onClick={() => decide(m, "confirm")} disabled={!(choice[m.id] ?? m.post_id)}>
                  Confirm
                </Button>
                <Button size="sm" variant="ghost" icon={<X className="size-4" />} onClick={() => decide(m, "reject")}>
                  Discard
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

export function Metrics() {
  const view = useDesk((s) => s.view);
  const route = useRoute();
  const tz = useTz();
  const posts = useMemo(() => (view?.posts ?? []).filter((p) => !p.id.startsWith("pending_")), [view?.posts]);
  const [open, setOpen] = useState<string | null>(route.query.get("post"));
  useEffect(() => setOpen(route.query.get("post")), [route.query]);
  const target = posts.find((p) => p.id === open);
  const close = () => {
    setOpen(null);
    if (route.query.get("post")) navigate("/metrics", { replace: true });
  };
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Metrics</h1>
        <p className="mt-1 text-sm text-muted">Sunday routine: upload screenshots, confirm anything flagged, and do the follower check-in. Manual numbers work anytime.</p>
      </header>
      <ReviewQueue posts={posts} />
      <div className="grid gap-5 xl:grid-cols-2">
        <Uploads />
        <CheckIn />
      </div>
      <Panel title="Posts" description="Latest numbers per post, and the reward relative to your median (1.0 = a typical post).">
        {posts.length === 0 ? (
          <Empty title="No posts yet">Mark a card as posted and it shows up here.</Empty>
        ) : (
          <div className="-mx-4 overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-[13px]">
              <thead className="text-[12px] text-muted">
                <tr className="border-b border-border">
                  <th className="px-4 py-2 font-medium">Post</th>
                  <th className="px-2 py-2 font-medium">Date</th>
                  <th className="px-2 py-2 text-right font-medium">Views</th>
                  <th className="px-2 py-2 text-right font-medium">Comments</th>
                  <th className="px-2 py-2 text-right font-medium">Reposts</th>
                  <th className="px-2 py-2 text-right font-medium">Edit</th>
                  <th className="px-2 py-2 text-right font-medium">Reward</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {posts.map((p) => (
                  <tr key={p.id} className="border-b border-border last:border-0">
                    <td className="max-w-xs px-4 py-2">
                      <span className="flex items-center gap-2">
                        <PlatformMark platform={p.platform} className="size-4 shrink-0 text-[9px]" />
                        <span className="truncate">{truncate(p.title || p.final_text, 70)}</span>
                      </span>
                    </td>
                    <td className="px-2 py-2 whitespace-nowrap text-muted">{formatDate(p.posted_at, tz)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{compact(p.latest_metrics?.impressions)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{num(p.latest_metrics?.comments)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{num(p.latest_metrics?.reposts)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{pct(p.edit_ratio)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{p.reward != null ? p.reward.toFixed(2) : "–"}</td>
                    <td className="px-4 py-2 text-right">
                      <Button size="sm" variant="ghost" onClick={() => setOpen(p.id)}>
                        {p.latest_metrics ? "Update" : "Add numbers"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <MetricsDialog post={target} open={!!target} onClose={close} />
    </div>
  );
}
