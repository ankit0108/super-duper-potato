import { useMemo, useState } from "react";
import { Check, Copy, ExternalLink, ImageIcon, LayoutGrid, Loader2, Send, Share2 } from "lucide-react";
import type { StudioPost, StudioVisual } from "@/lib/studio/blocks";
import type { StudioImage } from "@/lib/studio/chats";
import { imageFile } from "@/lib/studio/images";
import { copyText, linkedInComposeUrl, linkedInViaShareSheet, shareText, xComposeUrl } from "@/lib/compose";
import { POST_TYPE_LABEL } from "@/lib/format";
import { liveFlags } from "@/lib/guard";
import { withHashtags } from "@/lib/hashtags";
import { Link } from "@/lib/router";
import { useDesk } from "@/state/store";
import { Badge, PlatformMark } from "@/components/ui/Badge";
import { Button, cx } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Field";
import { canShareFiles } from "@/components/VisualViewer";
import { FeedPreview, LinkedInCounter, LiveChecks, ThreadEditor, XRing, replaceOpening } from "@/pages/card/Editor";
import { HashtagsBar } from "@/pages/card/Hashtags";
import { FirstComment } from "@/pages/card/FirstComment";
import { xWeightedLength } from "@/lib/text";
import { saveToBoard } from "./save";
import type { StudioEnv } from "./env";

export type VisualChoice = { key: string; label: string; visual: StudioVisual; photo: StudioImage | null };

const FORMAT_NAME = { li_text: "LinkedIn post", x_single: "X post", x_thread: "X thread" } as const;

/**
 * A post the Studio wrote: edit it, pick an opening and hashtags, see the live checks, then copy it, open the app
 * or save it to the board (with your pictures and a visual) to post and learn from like any other card.
 */
export function PostBlock({
  original,
  post,
  onChange,
  env,
  pictures,
  defaultPictures,
  visuals,
  defaultVisual,
  evidence,
  external,
  model,
  savedCardId,
  onSaved,
}: {
  original: StudioPost;
  post: StudioPost;
  onChange: (p: StudioPost) => void;
  env: StudioEnv;
  pictures: StudioImage[];
  defaultPictures: string[];
  visuals: VisualChoice[];
  defaultVisual: string | null;
  evidence: string;
  external: boolean;
  model: string | null;
  savedCardId?: string;
  onSaved: (cardId: string) => void;
}) {
  const toast = useDesk((s) => s.toast);
  const [picked, setPicked] = useState<string[]>(() => defaultPictures.filter((id) => pictures.some((p) => p.id === id)));
  const [visualKey, setVisualKey] = useState<string | null>(defaultVisual);
  const [saving, setSaving] = useState(false);
  const thread = post.format === "x_thread";
  const tags = post.hashtags;
  const tagLine = tags.join(" ");
  const composed = withHashtags(post.format, { text: post.text, posts: post.posts }, tags);
  const full = thread ? composed.posts.filter((p) => p.trim()).join("\n\n") : composed.text;
  const body = thread ? post.posts.join("\n\n") : post.text;
  const chosenPictures = pictures.filter((p) => picked.includes(p.id));
  const visual = visuals.find((v) => v.key === visualKey) ?? null;
  const flags = useMemo(
    () =>
      liveFlags({
        text: body,
        evidence,
        guardTerms: env.guardTerms,
        avoid: env.avoid,
        bait: env.bait,
        external,
        platform: { platform: post.platform, format: post.format, hashtags: tags.length, fold: env.fold },
        postType: post.post_type,
      }),
    [body, evidence, env, external, post.platform, post.format, post.post_type, tags.length],
  );
  const blocked = flags.blocked.length > 0;
  const flagged = Object.values(flags).reduce((n, v) => n + (Array.isArray(v) ? v.length : 0), 0);

  const set = (patch: Partial<StudioPost>) => onChange({ ...post, ...patch });
  const applyHook = (hook: string) => (thread ? set({ posts: [replaceOpening(post.posts[0] ?? "", hook), ...post.posts.slice(1)] }) : set({ text: replaceOpening(post.text, hook) }));
  const files = () => chosenPictures.map(imageFile);
  const sharesFiles = useMemo(() => typeof File !== "undefined" && canShareFiles([new File([""], "x.jpg", { type: "image/jpeg" })]), []);
  const withFiles = chosenPictures.length > 0 && sharesFiles;

  const copy = async () => {
    const ok = await copyText(full);
    toast(ok ? "ok" : "bad", ok ? "Copied. Paste it into the app." : "Couldn't copy. Select the text and copy it manually.");
  };
  const open = () => {
    const nudge = savedCardId ? undefined : { label: "Save to board", onAction: () => void save() };
    const after = savedCardId ? "Posted it? Mark it posted on the card so PBS learns from it." : "Posted it? Save it to the board and mark it posted there, so PBS learns from how it does.";
    if (withFiles) {
      // On a phone: the share sheet takes the text and the pictures to the app's composer together.
      const copied = copyText(full);
      void navigator
        .share({ text: full, files: files() })
        .then(() => toast("ok", after, nudge))
        .catch(async (e) => {
          if ((e as Error)?.name === "AbortError") return;
          toast("bad", (await copied) ? "Couldn't share. The text is copied: open the app and paste it." : "Couldn't share or copy.");
        });
      return;
    }
    if (post.platform === "linkedin" && linkedInViaShareSheet()) {
      const copied = copyText(full);
      void shareText(full).then(async (r) => {
        if (r === "shared") return toast("ok", after, nudge);
        if (r === "failed") toast("ok", (await copied) ? "Copied. Open LinkedIn and paste it into a new post." : "Couldn't share or copy.");
      });
      return;
    }
    window.open(post.platform === "linkedin" ? linkedInComposeUrl(full) : xComposeUrl(thread ? (composed.posts[0] ?? "") : full), "_blank", "noopener");
    toast("info", after, nudge);
  };
  const save = async () => {
    if (savedCardId || saving) return;
    setSaving(true);
    try {
      const id = await saveToBoard({ post, hashtags: tags, images: chosenPictures, visual: visual?.visual ?? null, photo: visual?.visual.use_photo ? visual.photo : null, evidence, model, kit: env.kit });
      onSaved(id);
    } catch (e) {
      toast("bad", `Couldn't save: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  const xUsed = xWeightedLength(tagLine ? `${post.text.trimEnd()} ${tagLine}` : post.text);
  return (
    <section aria-label={FORMAT_NAME[post.format]} className="space-y-3 rounded-2xl border border-border bg-surface p-3 shadow-sm">
      <header className="flex flex-wrap items-center gap-2">
        <PlatformMark platform={post.platform} />
        <h3 className="text-[13px] font-semibold">
          {FORMAT_NAME[post.format]}
          {thread && ` · ${post.posts.length} posts`}
        </h3>
        {post.post_type && POST_TYPE_LABEL[post.post_type] && <Badge tone="accent">{POST_TYPE_LABEL[post.post_type]}</Badge>}
        {post.pillar && env.pillars[post.platform]?.[post.pillar] && <Badge tone="neutral">{env.pillars[post.platform][post.pillar]}</Badge>}
        {savedCardId && (
          <Badge tone="ok" icon={<Check className="size-3" />}>
            On the board
          </Badge>
        )}
      </header>

      {thread ? (
        <ThreadEditor posts={post.posts} onChange={(posts) => set({ posts })} limit={env.xLimit} min={env.threadMin} max={env.threadMax} firstSuffix={tagLine} />
      ) : (
        <div className={cx("rounded-2xl border bg-surface focus-within:ring-2 focus-within:ring-accent/15", post.platform === "x" && xUsed > env.xLimit ? "border-bad/50" : "border-border focus-within:border-accent")}>
          <Textarea aria-label={`${FORMAT_NAME[post.format]} text`} value={post.text} onChange={(e) => set({ text: e.target.value })} minRows={post.platform === "x" ? 3 : 6} className="border-0 bg-transparent text-[15px] shadow-none focus:ring-0" />
          <div className="flex items-center justify-end gap-2 border-t border-border px-2 py-1">
            {post.platform === "x" ? <XRing used={xUsed} limit={env.xLimit} /> : <LinkedInCounter text={tagLine ? `${post.text.trimEnd()}\n\n${tagLine}` : post.text} limit={env.liLimit} />}
          </div>
        </div>
      )}

      {post.hooks.length > 0 && (
        <div className="space-y-1.5">
          <h4 className="text-[12.5px] font-semibold text-muted">Other openings</h4>
          <ul className="space-y-1.5">
            {post.hooks.map((h) => (
              <li key={h} className="flex items-start gap-2 rounded-xl border border-border px-2.5 py-2">
                <p className="min-w-0 flex-1 text-[13.5px] leading-snug">{h}</p>
                <Button size="sm" variant="secondary" onClick={() => applyHook(h)} aria-label={`Use opening: ${h}`}>
                  Use
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {post.platform === "linkedin" && !thread && (
        <details className="text-[13px]">
          <summary className="cursor-pointer text-muted">How it shows in the feed</summary>
          <div className="mt-2">
            <FeedPreview text={post.text} fold={env.fold} />
          </div>
        </details>
      )}

      {(original.hashtags.length > 0 || tags.length > 0) && <HashtagsBar platform={post.platform} suggested={original.hashtags} chosen={tags} onChange={(hashtags) => set({ hashtags })} />}
      {post.first_comment && <FirstComment platform={post.platform} text={post.first_comment} />}

      {pictures.length > 0 && (
        <div className="space-y-1.5">
          <h4 className="flex items-center gap-1.5 text-[12.5px] font-semibold text-muted">
            <ImageIcon className="size-3.5" aria-hidden /> Pictures to post with it
          </h4>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Pictures to post with it">
            {pictures.map((p, i) => {
              const on = picked.includes(p.id);
              return (
                <button
                  key={p.id}
                  type="button"
                  aria-pressed={on}
                  aria-label={`Picture ${i + 1}${on ? ", included" : ""}`}
                  onClick={() => setPicked((cur) => (on ? cur.filter((x) => x !== p.id) : [...cur, p.id]))}
                  className={cx("relative size-16 overflow-hidden rounded-lg border-2", on ? "border-accent" : "border-transparent opacity-60 hover:opacity-100")}
                >
                  <img src={p.dataUrl} alt="" className="size-full object-cover" />
                  {on && <Check className="absolute top-0.5 right-0.5 size-4 rounded-full bg-accent p-0.5 text-accent-fg" aria-hidden />}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {visuals.length > 0 && (
        <label className="flex flex-wrap items-center gap-2 text-[13px]">
          <LayoutGrid className="size-4 text-muted" aria-hidden />
          <span className="font-medium">Visual</span>
          <select value={visualKey ?? ""} onChange={(e) => setVisualKey(e.target.value || null)} className="h-8 rounded-lg border border-border bg-surface px-2 text-[13px]" aria-label="Visual to save with it">
            <option value="">None</option>
            {visuals.map((v) => (
              <option key={v.key} value={v.key}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
      )}

      <details open={blocked} className="rounded-xl border border-border px-3 py-2">
        <summary className={cx("cursor-pointer text-[13px] font-medium", blocked ? "text-bad" : flagged ? "text-warn" : "text-ok")}>{blocked ? "Matches your guard terms: fix before posting" : flagged ? `Checks: ${flagged} thing${flagged === 1 ? "" : "s"} to look at` : "Checks: nothing flagged"}</summary>
        <div className="mt-2">
          <LiveChecks flags={flags} hasGuardTerms={env.guardTerms.length > 0} />
        </div>
      </details>

      {post.sources.length > 0 && (
        <div className="text-[12.5px] text-muted">
          Sources:{" "}
          {post.sources.map((s, i) => (
            <span key={s.url}>
              {i > 0 && " · "}
              <a href={s.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                {s.title || new URL(s.url).hostname}
              </a>
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        {savedCardId ? (
          <Link to={`/card/${savedCardId}`} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-2.5 text-[13px] font-medium text-accent-fg">
            <ExternalLink className="size-4" aria-hidden /> Open the card
          </Link>
        ) : (
          <Button size="sm" variant="primary" icon={saving ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} onClick={() => void save()} disabled={saving || blocked || !body.trim()}>
            Save to board
          </Button>
        )}
        <Button size="sm" icon={<Copy className="size-4" />} onClick={() => void copy()} disabled={!body.trim()}>
          Copy
        </Button>
        <Button size="sm" icon={withFiles ? <Share2 className="size-4" /> : <ExternalLink className="size-4" />} onClick={open} disabled={!body.trim() || blocked}>
          {withFiles ? "Share with pictures" : post.platform === "linkedin" ? "Open LinkedIn" : "Open X"}
        </Button>
      </div>
    </section>
  );
}
