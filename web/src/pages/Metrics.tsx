import { useEffect, useMemo, useState } from "react";
import { Check, FileUp, History, Loader2, RefreshCw, Sparkles, X } from "lucide-react";
import type { Metric, MetricUpload, MetricValues, Platform, Post } from "@/types";
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

// Analytics exports are sent as they are and read exactly by the pipeline; screenshots are shrunk first.
const EXPORT = /\.(xlsx|csv)$/i;
const MAX_EXPORT_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/*,.xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv";
const PLATFORM_NAME: Record<string, string> = { linkedin: "LinkedIn", x: "X" };

export function isExport(file: { name: string }): boolean {
  return EXPORT.test(file.name);
}

type FileResult = { path?: string; kind?: string; platform?: string | null; metrics?: number; matched?: number; history?: number; needs_review?: number; links_saved?: number; days?: number; audience?: number; followers?: number | null; error?: string };

/** What an upload's files gave, in a line each ("LinkedIn export: 24 posts, 3 yours, 21 earlier"). */
export function uploadSummary(u: MetricUpload): string[] {
  const files = ((u.results as { files?: FileResult[] } | null | undefined)?.files ?? []) as FileResult[];
  return files.map((f) => {
    if (f.error) return f.error;
    if (f.kind === "file") {
      const name = PLATFORM_NAME[f.platform ?? ""] ?? "Analytics";
      const posts = (f.matched ?? 0) + (f.history ?? 0) + (f.needs_review ?? 0);
      const parts = [
        posts ? `${posts} post${posts === 1 ? "" : "s"}` : null,
        f.matched ? `${f.matched} matched to PBS posts` : null,
        f.history ? `${f.history} earlier` : null,
        f.needs_review ? `${f.needs_review} to check` : null,
        f.links_saved ? `links saved to ${f.links_saved} post${f.links_saved === 1 ? "" : "s"}` : null,
        f.days ? `${f.days} days of totals` : null,
        f.followers != null ? `${num(f.followers)} followers` : null,
        f.audience ? "audience" : null,
      ].filter(Boolean);
      return `${name} export: ${parts.join(", ") || "nothing new"}`;
    }
    return `Screenshot: ${f.metrics ?? 0} number set${f.metrics === 1 ? "" : "s"}${f.needs_review ? `, ${f.needs_review} to check` : ""}`;
  });
}

function Uploads() {
  const act = useDesk((s) => s.act);
  const upload = useDesk((s) => s.uploadBlob);
  const toast = useDesk((s) => s.toast);
  const mode = useDesk((s) => s.connection?.mode);
  const uploads = useDesk((s) => s.view?.uploads) ?? NONE;
  const tz = useTz();
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [showHow, setShowHow] = useState(false);
  const exports = files.filter(isExport).length;
  const choose = (list: File[]) => {
    const tooBig = list.find((f) => isExport(f) && f.size > MAX_EXPORT_BYTES);
    if (tooBig) toast("bad", `${tooBig.name} is over 10 MB: export a shorter date range.`);
    setFiles(list.filter((f) => !(isExport(f) && f.size > MAX_EXPORT_BYTES)).slice(0, 20));
  };
  const send = async () => {
    if (!files.length) return;
    setBusy(true);
    const uploadId = newId("upl");
    const paths: string[] = [];
    try {
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        const ext = isExport(f) ? f.name.toLowerCase().match(EXPORT)![1] : "jpg";
        const bytes = isExport(f) ? new Uint8Array(await f.arrayBuffer()) : await compressImage(f);
        const path = `inbox/blobs/${uploadId}_${i + 1}.${ext}`;
        await upload(path, bytes, isExport(f) ? "desk: analytics export" : "desk: analytics screenshot");
        paths.push(path);
      }
      const note = exports ? `${exports} export${exports === 1 ? "" : "s"}${files.length > exports ? ` and ${files.length - exports} screenshot(s)` : ""}` : null;
      act(
        // The week only names the folder the files are kept in; an export says its own period.
        { type: "metrics.upload", upload_id: uploadId, paths, week: isoWeek(new Date()), note },
        { toast: mode === "demo" ? "Demo: upload simulated." : "Uploaded. The numbers and a fresh review appear after the next run (a few minutes)." },
      );
      setFiles([]);
    } catch (e) {
      toast("bad", `Upload failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel
      title="Upload analytics"
      description="LinkedIn's Excel export or X's CSV export: every number is read exactly, straight from the file. Screenshots work too; a model reads those."
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-border-strong px-4 py-3 text-sm hover:bg-surface-2">
          <FileUp className="size-5 text-muted" aria-hidden />
          <span>{files.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "Choose .xlsx, .csv or screenshots"}</span>
          <input type="file" accept={ACCEPT} multiple className="sr-only" aria-label="Analytics files" onChange={(e) => choose(Array.from(e.target.files ?? []))} />
        </label>
        <Button variant="primary" onClick={() => void send()} loading={busy} disabled={!files.length}>
          Upload
        </Button>
      </div>
      {files.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-muted">
          {files.map((f) => (
            <li key={`${f.name}-${f.size}`} className="truncate">
              {isExport(f) ? "Export" : "Screenshot"}: {f.name}
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="mt-3 text-[13px] text-accent hover:underline" onClick={() => setShowHow((v) => !v)} aria-expanded={showHow}>
        {showHow ? "Hide" : "Where do I get the export?"}
      </button>
      {showHow && (
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[13px] text-muted">
          <li>
            <span className="text-fg">LinkedIn:</span> open your analytics (Me → Analytics, or “View analytics” under any of your posts), pick a date range and choose <span className="text-fg">Export</span>. You get an .xlsx file: upload it as it is. A longer range (90 or 365 days) gives the review more to go on.
          </li>
          <li>
            <span className="text-fg">One post:</span> the analytics page of a single post has its own Export too.
          </li>
          <li>
            <span className="text-fg">X:</span> Analytics → <span className="text-fg">Export data</span> gives a .csv of your posts (X keeps analytics for Premium accounts).
          </li>
          <li>Posts you made before PBS count too: they're kept for the review, not mixed into the learning about PBS's drafts.</li>
        </ul>
      )}
      {uploads.length > 0 && (
        <ul className="mt-4 divide-y divide-border text-[13px]">
          {uploads.slice(0, 6).map((u) => (
            <li key={u.id} className="py-2">
              <div className="flex items-center justify-between gap-2">
                <span>
                  {u.paths?.length ?? 0} file{u.paths?.length === 1 ? "" : "s"} · {formatDate(u.created_at, tz)}
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
              </div>
              {u.status === "processed" &&
                uploadSummary(u).map((line, i) => (
                  <p key={i} className="mt-0.5 text-xs text-muted">
                    {line}
                  </p>
                ))}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

const PRO = "gemini_pro";
const PROVIDER_NAME: Record<string, string> = { gemini_pro: "Gemini Pro", gemini: "Gemini Flash", gemini_lite: "Gemini Flash-Lite", groq: "Groq", openrouter: "OpenRouter" };
const WHY: Record<string, string> = { quota: "no free quota left on your key", busy: "busy (server overloaded)", error: "an error" };

/** Who wrote the review, in words: the model's name, and why the stronger ones didn't when it wasn't Gemini Pro. */
export function reviewAuthor(p: { model?: string | null; provider?: string | null; passed_over?: Array<Record<string, string>> | null; retry?: boolean | null }): { model: string; note: string | null } {
  const model = p.model ?? "a model";
  if (p.provider === PRO) return { model, note: null };
  const passed = (p.passed_over ?? []).map((x) => `${PROVIDER_NAME[x.provider] ?? x.provider}: ${WHY[x.why] ?? x.why}`);
  const why = passed.length ? `Passed over: ${passed.join("; ")}.` : "Gemini Pro (the strongest free model) wasn't available on the key today, so the next best one wrote it.";
  return { model, note: p.retry ? `${why} A stronger model tries again on the next run.` : why };
}

function List({ title, items, tone }: { title: string; items?: string[] | null; tone: "ok" | "bad" | "info" }) {
  if (!items?.length) return null;
  const mark = tone === "ok" ? "text-ok" : tone === "bad" ? "text-bad" : "text-accent";
  return (
    <div>
      <h3 className="text-[13px] font-semibold">{title}</h3>
      <ul className="mt-1.5 space-y-1 text-[13.5px]">
        {items.map((t, i) => (
          <li key={i} className="flex gap-2">
            <span className={mark} aria-hidden>
              {tone === "ok" ? "+" : tone === "bad" ? "−" : "→"}
            </span>
            <span>{t}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Performance() {
  const act = useDesk((s) => s.act);
  const review = useDesk((s) => s.view?.performance);
  const requested = useDesk((s) => s.pending.runRequested.includes("analysis"));
  const tz = useTz();
  const again = (
    <Button
      size="sm"
      variant="ghost"
      icon={<RefreshCw className="size-4" />}
      disabled={requested}
      onClick={() => act({ type: "run.request", tasks: ["analysis"] }, { toast: "Asked for a fresh review. It appears after the run." })}
    >
      {requested ? "Requested" : "Analyse again"}
    </Button>
  );
  const title = (
    <span className="flex items-center gap-1.5">
      <Sparkles className="size-4 text-accent" aria-hidden /> What your numbers say
    </span>
  );
  if (!review || review.status === "too_little" || (!review.headline && review.status !== "ok")) {
    return (
      <Panel title={title} description="A review of how your posts perform, written from your analytics by Gemini Pro, the strongest model on the free key (the next best one when Pro isn't available)." actions={review ? again : undefined}>
        <p className="text-[13.5px] text-muted">
          {review?.status === "waiting"
            ? `Waiting for model quota: ${review.error ?? "it tries again on the next run"}.`
            : review?.status === "failed"
              ? `${review.error ?? "No model could write the review"}. It tries again after the next upload, or ask with Analyse again.`
              : review?.headline || "Upload LinkedIn's or X's export below. After the next run, the review appears here: what's working, what isn't, and what to try next."}
        </p>
      </Panel>
    );
  }
  const author = reviewAuthor(review);
  return (
    <Panel title={title} actions={again}>
      <div className="space-y-4">
        <p className="text-[15px] font-medium leading-snug">{review.headline}</p>
        {Object.keys(review.coverage ?? {}).length > 0 && <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(review.coverage ?? {}).map(([platform, c]) => <div key={platform} className="rounded-xl border border-border p-3 text-[13px]">
            <p className="font-semibold">{platform === "linkedin" ? "LinkedIn" : "X"} data coverage</p>
            <p>{c.measured} of {c.published} PBS posts have confirmed impressions. {c.missing} unmeasured; {c.needs_review} measurements to review.</p>
            {c.measured === 0 && <p className="mt-1 text-muted">Upload this platform's analytics before drawing performance conclusions.</p>}
            {c.latest_capture && <p className="mt-1 text-xs text-muted">Last measured {formatDate(c.latest_capture, tz)}</p>}
          </div>)}
        </div>}
        {(review.findings?.length ?? 0) > 0 && (
          <ol className="space-y-3">
            {review.findings!.map((f, i) => (
              <li key={i} className="rounded-xl border border-border p-3">
                <p className="text-[14px] font-semibold">{f.title}</p>
                {f.detail && <p className="mt-0.5 text-[13.5px]">{f.detail}</p>}
                {f.evidence && <p className="mt-1 text-xs text-muted tabular-nums">{f.evidence}</p>}
              </li>
            ))}
          </ol>
        )}
        <div className="grid gap-4 md:grid-cols-3">
          <List title="Keep doing" items={review.what_works} tone="ok" />
          <List title="Change or drop" items={review.what_doesnt} tone="bad" />
          <List title="Try in the next two weeks" items={review.try_next} tone="info" />
        </div>
        {review.audience && (
          <p className="text-[13.5px]">
            <span className="font-semibold">Who's reading: </span>
            {review.audience}
          </p>
        )}
        {(review.caveats?.length ?? 0) > 0 && <p className="text-xs text-muted">Keep in mind: {review.caveats!.join(" ")}</p>}
        <p className="border-t border-border pt-3 text-xs text-muted">
          Written by <span className="font-medium text-fg">{author.model}</span> on {formatDate(review.at, tz)} from {review.posts} post{review.posts === 1 ? "" : "s"}
          {review.period ? ` (${review.period})` : ""}. {author.note}
          {review.error ? ` The last try didn't work (${review.error}); this is the previous review.` : ""}
        </p>
      </div>
    </Panel>
  );
}

function ReviewQueue({ posts }: { posts: Post[] }) {
  const act = useDesk((s) => s.act);
  const metrics = useDesk((s) => s.view?.metrics);
  const queue = useMemo(() => (metrics ?? []).filter((m) => m.status === "needs_review"), [metrics]);
  const [choice, setChoice] = useState<Record<string, string>>({});
  if (!queue.length) return null;
  const decide = (m: Metric, action: "confirm" | "reject" | "history") => {
    const postId = choice[m.id] ?? m.post_id ?? "";
    act(
      { type: "metrics.review", metric_id: m.id, action, ...(action === "confirm" && postId ? { post_id: postId } : {}) },
      { toast: action === "confirm" ? "Confirmed." : action === "history" ? "Kept for the review, not as a PBS post." : "Discarded." },
    );
  };
  return (
    <Panel title={`Check ${queue.length} set${queue.length === 1 ? "" : "s"} of numbers`} description="PBS wasn't sure which post these belong to. Pick the post and confirm.">
      <ul className="space-y-3">
        {queue.map((m) => {
          const fields = METRIC_FIELDS[(m.platform as Platform) ?? "linkedin"].filter((f) => m[f.key] != null);
          const raw = (m.raw ?? {}) as { text_snippet?: string; url?: string | null; posted_date?: string | null };
          const fromFile = m.source === "file";
          const snippet = raw.text_snippet && raw.text_snippet !== raw.url ? raw.text_snippet : null;
          return (
            <li key={m.id} className="rounded-xl border border-border p-3">
              {fromFile ? (
                <p className="text-[13px] text-muted">
                  From your export{raw.posted_date ? `, posted ${raw.posted_date}` : ""}
                  {snippet ? `: “${snippet}”` : ""}
                  {raw.url && (
                    <>
                      {" "}
                      <a href={raw.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                        open the post
                      </a>
                    </>
                  )}
                </p>
              ) : (
                snippet && <p className="text-[13px] text-muted">Screenshot text: “{snippet}”</p>
              )}
              <p className="mt-1 text-[13px]">{fields.map((f) => `${f.label}: ${num(m[f.key] as number)}`).join(" · ")}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Select aria-label="Which post" value={choice[m.id] ?? m.post_id ?? ""} onChange={(e) => setChoice((c) => ({ ...c, [m.id]: e.target.value }))} className="h-9 w-full min-w-0 sm:w-auto sm:max-w-md sm:flex-1">
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
                {fromFile && (
                  <Button size="sm" variant="ghost" icon={<History className="size-4" />} onClick={() => decide(m, "history")}>
                    Not a PBS post
                  </Button>
                )}
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
        <p className="mt-1 text-sm text-muted">Weekly routine: upload LinkedIn's and X's analytics exports (or screenshots), confirm anything flagged, and read what the numbers say. Manual numbers work anytime.</p>
      </header>
      <ReviewQueue posts={posts} />
      <Performance />
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
