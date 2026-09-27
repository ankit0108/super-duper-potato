import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Copy, ExternalLink, GitCompare, Loader2, RotateCcw, Send, Sparkle, Undo2 } from "lucide-react";
import type { Card } from "@/types";
import { FORMAT_LABEL, PLATFORM_LABEL, SKIP_REASONS, draftText, pct } from "@/lib/format";
import { copyText, linkedInComposeUrl, safeUrl, xComposeUrl } from "@/lib/compose";
import { liveFlags, parseTerms } from "@/lib/guard";
import { navigate, Link } from "@/lib/router";
import { editRatio } from "@/lib/text";
import { formatDateTime } from "@/lib/time";
import { useDesk } from "@/state/store";
import { useCard, useEditingTimer, usePillarLabels, useTz } from "@/state/hooks";
import { evidenceFor } from "@/state/selectors";
import { Badge, PlatformMark, StatusBadge } from "@/components/ui/Badge";
import { Button, LinkButton, cx } from "@/components/ui/Button";
import { Banner, Empty, Panel } from "@/components/ui/Feedback";
import { Tabs } from "@/components/ui/Tabs";
import { FlagIcons, SkipMenu, workLabel } from "@/components/card/CardTile";
import { DiffPanel, HooksPanel, LinkedInEditor, LiveChecks, ThreadEditor, XPostEditor, numbered, replaceOpening } from "./card/Editor";
import { Details, PipelineFlags, ReplyHelper, Sources, WhyAngle } from "./card/Context";
import { PostedDialog, RewriteDialog, type PostedPayload } from "./card/Dialogs";
import { Interview } from "./card/Interview";
import { useWorkingCopy } from "./card/useWorkingCopy";

export function CardPage({ id }: { id: string }) {
  const card = useCard(id);
  if (!card) {
    return (
      <Empty title="Card not found" action={<Link to="/" className="text-accent hover:underline">Back to the board</Link>}>
        It may have expired and left the desk's recent window. Older cards are on the History page.
      </Empty>
    );
  }
  return <CardView key={card.id} card={card} />;
}

function CardView({ card }: { card: Card }) {
  const act = useDesk((s) => s.act);
  const toast = useDesk((s) => s.toast);
  const view = useDesk((s) => s.view);
  const guardRaw = useDesk((s) => s.guardTerms);
  const pendingCard = useDesk((s) => s.pending.cards.has(card.id));
  const tz = useTz();
  const pillar = usePillarLabels();
  const wc = useWorkingCopy(card);
  const editable = ["suggested", "editing", "blocked"].includes(card.status) && !!card.draft;
  const [seconds] = useEditingTimer(card.id, editable);
  const [posting, setPosting] = useState(false);
  const [rewriting, setRewriting] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [side, setSide] = useState<"context" | "sources" | "checks" | "details">("context");
  const startedEditing = useRef(card.status === "editing");

  const settings = view?.settings as Record<string, any> | undefined;
  const xLimit = settings?.platforms?.x?.premium ? settings?.platforms?.x?.premium_char_limit ?? 25000 : settings?.platforms?.x?.char_limit ?? 280;
  const liLimit = settings?.platforms?.linkedin?.char_limit ?? 3000;
  const fold = settings?.platforms?.linkedin?.fold_chars ?? 210;
  const threadMin = settings?.platforms?.x?.thread_min ?? 3;
  const threadMax = settings?.platforms?.x?.thread_max ?? 7;
  const avoid = useMemo(() => [...(settings?.voice?.avoid_phrases ?? []), ...(view?.voice?.avoid ?? [])], [settings, view?.voice]);
  const bait: string[] = settings?.voice?.bait_phrases ?? [];
  const guardTerms = useMemo(() => parseTerms(guardRaw), [guardRaw]);
  const baseline = draftText(card);
  const text = wc.finalText;
  const flags = useMemo(
    () => liveFlags({ text, evidence: evidenceFor(card), guardTerms, avoid, bait, external: card.mode === "external" }),
    [text, card, guardTerms, avoid, bait],
  );

  // First keystroke picks the card (the ranker learns from picks).
  const markEditing = useCallback(() => {
    if (!startedEditing.current && card.status === "suggested") {
      startedEditing.current = true;
      act({ type: "card.status", card_id: card.id, status: "editing" });
    }
  }, [act, card.id, card.status]);

  // Save edits to the pipeline when leaving (or when switching to the LinkedIn/X app).
  const latest = useRef({ wc, card });
  latest.current = { wc, card };
  useEffect(() => {
    const sync = () => {
      const { wc: w, card: c } = latest.current;
      if (!w.dirtyVsServer || !["suggested", "editing", "blocked"].includes(c.status)) return;
      act({
        type: "card.edit",
        card_id: c.id,
        ...(c.format === "x_thread" ? { posts: w.copy.posts } : { text: w.copy.text }),
        hook_index: w.copy.hookIndex,
      });
    };
    const onHide = () => document.visibilityState === "hidden" && sync();
    document.addEventListener("visibilitychange", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      sync();
    };
  }, [act]);

  const setText = (v: string) => {
    markEditing();
    wc.update({ text: v });
  };
  const setPosts = (p: string[]) => {
    markEditing();
    wc.update({ posts: p });
  };
  const useHook = (i: number) => {
    const hook = card.hooks?.[i]?.text;
    if (!hook) return;
    markEditing();
    if (card.format === "x_thread") {
      const posts = [...wc.copy.posts];
      posts[0] = replaceOpening(posts[0] ?? "", hook);
      wc.update({ posts, hookIndex: i });
    } else {
      wc.update({ text: replaceOpening(wc.copy.text, hook), hookIndex: i });
    }
    act({ type: "card.hook", card_id: card.id, hook_index: i });
  };

  const copyAll = async () => {
    const ok = await copyText(card.format === "x_thread" ? numbered(wc.copy.posts.filter((p) => p.trim())).join("\n\n") : text);
    toast(ok ? "ok" : "bad", ok ? "Copied. Paste it into the app, then come back and tap Posted." : "Couldn't copy. Select the text and copy it manually.");
  };
  const composeUrl =
    card.platform === "linkedin"
      ? linkedInComposeUrl(text)
      : xComposeUrl(card.format === "x_thread" ? (wc.copy.posts[0] ?? "") : text, card.format === "x_quote" ? safeUrl(card.draft?.quote_url) : undefined);

  const confirmPosted = (p: PostedPayload) => {
    act(
      {
        type: "card.posted",
        card_id: card.id,
        ...(card.format === "x_thread" && p.posts ? { posts: p.posts } : { text: p.text }),
        post_url: p.post_url,
        posted_at: p.posted_at,
        editing_seconds: p.editing_seconds,
        hook_index: wc.copy.hookIndex,
      },
      { toast: baseline ? `Posted. You changed ${pct(editRatio(baseline, p.text))} of the draft.` : "Posted." },
    );
    wc.clear();
    setPosting(false);
    navigate("/");
  };

  const confirmRewrite = (r: { note: string; chips: string[]; target_platform?: Card["platform"]; target_format?: Card["format"] }) => {
    const events = [];
    if (wc.dirtyVsServer) {
      events.push({
        type: "card.edit" as const,
        card_id: card.id,
        ...(card.format === "x_thread" ? { posts: wc.copy.posts } : { text: wc.copy.text }),
        hook_index: wc.copy.hookIndex,
      });
    }
    events.push({ type: "card.rewrite" as const, card_id: card.id, note: r.note, chips: r.chips, target_platform: r.target_platform ?? null, target_format: r.target_format ?? null });
    act(events, { toast: r.target_platform ? "Adapting it. The new card appears on the board in about two minutes." : "Rewrite requested. The new draft arrives in about two minutes." });
    setRewriting(false);
  };

  // Keyboard: Cmd/Ctrl+Enter → Posted, Cmd/Ctrl+Shift+C → copy.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key === "Enter" && editable) {
        e.preventDefault();
        setPosting(true);
      }
      if (mod && e.shiftKey && (e.key === "C" || e.key === "c") && editable) {
        e.preventDefault();
        void copyAll();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const work = workLabel(card);
  const post = card.post_id ? view?.posts?.find((p) => p.id === card.post_id) : undefined;
  const isInterview = card.status === "needs_input" && !card.draft;
  const isBrief = card.draft_state === "brief" && !card.draft;

  const sidePanel = (
    <div className="space-y-4">
      <Tabs
        compact
        label="Card context"
        value={side}
        onChange={setSide}
        items={[
          { value: "context", label: "Context" },
          { value: "sources", label: "Sources", count: card.sources?.length },
          { value: "checks", label: "Checks" },
          { value: "details", label: "Details" },
        ]}
      />
      {side === "context" && (
        <div className="space-y-4">
          <ReplyHelper card={card} />
          <WhyAngle card={card} />
        </div>
      )}
      {side === "sources" && <Sources card={card} />}
      {side === "checks" && (
        <div className="space-y-4">
          {editable && <LiveChecks flags={flags} hasGuardTerms={guardTerms.length > 0} />}
          <div className="space-y-2">
            <h3 className="text-[13px] font-semibold">Pipeline checks</h3>
            <PipelineFlags card={card} />
          </div>
        </div>
      )}
      {side === "details" && <Details card={card} />}
    </div>
  );

  return (
    <div className="pb-20 lg:pb-0">
      <div className="mb-4 flex items-center gap-2">
        <Button variant="ghost" size="sm" icon={<ArrowLeft className="size-4" />} onClick={() => (history.length > 1 ? history.back() : navigate("/"))}>
          Back
        </Button>
      </div>
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-1.5">
          <PlatformMark platform={card.platform} />
          <span className="text-[13px] font-medium text-muted">{PLATFORM_LABEL[card.platform]}</span>
          {card.rank != null && card.kind === "news" && <Badge tone="neutral">#{card.rank} today</Badge>}
          <Badge tone="neutral">{pillar(card.platform, card.pillar)}</Badge>
          <Badge tone="neutral">{FORMAT_LABEL[card.format]}</Badge>
          <StatusBadge status={card.status} />
          {card.explore && <Badge tone="accent">{card.experiment_id ? "Experiment" : "Exploring"}</Badge>}
          {pendingCard && <Badge tone="neutral">Syncing</Badge>}
          <FlagIcons card={card} />
        </div>
        <h1 className="mt-2 text-xl leading-snug font-semibold tracking-tight">{card.title}</h1>
      </header>

      {work && (
        <div className="mb-4">
          <Banner tone="info">
            <span className="inline-flex items-center gap-2">
              <Loader2 className="size-4 animate-spin" /> {work} The pipeline is on it; this page updates by itself.
            </span>
            {card.work?.last_error && <span className="block text-xs text-muted">{card.work.last_error}</span>}
          </Banner>
        </div>
      )}
      {wc.newDraft && (
        <div className="mb-4">
          <Banner
            tone="info"
            action={
              <div className="flex gap-1.5">
                <Button size="sm" variant="primary" onClick={wc.acceptNewDraft}>
                  Use new draft
                </Button>
                <Button size="sm" variant="secondary" onClick={wc.keepMine}>
                  Keep my edits
                </Button>
              </div>
            }
          >
            A new version arrived (your rewrite, or edits from another device).
          </Banner>
        </div>
      )}
      {card.status === "blocked" && (
        <div className="mb-4">
          <Banner tone="bad">
            Blocked: the draft mentions a term from your blocklist ({(card.flags?.blocked ?? []).join(", ")}). Remove it before posting, or skip the card.
          </Banner>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-5">
          {isInterview ? (
            <Panel>
              <Interview card={card} />
            </Panel>
          ) : isBrief ? (
            <Panel title="No draft yet" description="The free model quota ran out when this card was delivered.">
              <div className="space-y-3 text-sm">
                <p>
                  <b>Angle:</b> {card.angle}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button variant="primary" icon={<Sparkle className="size-4" />} disabled={!!card.work} onClick={() => act({ type: "card.draft_now", card_id: card.id }, { toast: "Drafting it now." })}>
                    Draft this
                  </Button>
                </div>
              </div>
            </Panel>
          ) : card.status === "posted" ? (
            <PostedSummary card={card} post={post} tz={tz} />
          ) : ["skipped", "expired", "failed"].includes(card.status) ? (
            <Panel
              title={card.status === "skipped" ? "Skipped" : card.status === "failed" ? "Drafting failed" : "Expired"}
              description={card.status === "skipped" ? SKIP_REASONS.find((r) => r.value === card.skip?.reason)?.label + (card.skip?.note ? ` — ${card.skip.note}` : "") : undefined}
              actions={
                <Button size="sm" icon={<Undo2 className="size-4" />} onClick={() => act({ type: "card.restore", card_id: card.id }, { toast: "Restored." })}>
                  Restore
                </Button>
              }
            >
              <p className="draft-text text-[14px] text-muted">{baseline || card.angle}</p>
            </Panel>
          ) : (
            <>
              {card.format === "li_text" ? (
                <LinkedInEditor value={wc.copy.text} onChange={setText} limit={liLimit} fold={fold} />
              ) : card.format === "x_thread" ? (
                <ThreadEditor posts={wc.copy.posts} onChange={setPosts} limit={xLimit} min={threadMin} max={threadMax} />
              ) : (
                <XPostEditor value={wc.copy.text} onChange={setText} limit={xLimit} label={`${FORMAT_LABEL[card.format]} text`} minRows={5} />
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" variant={showDiff ? "soft" : "ghost"} icon={<GitCompare className="size-4" />} onClick={() => setShowDiff((v) => !v)} aria-pressed={showDiff}>
                  {showDiff ? "Hide changes" : "Show changes"}
                </Button>
                <Button size="sm" variant="ghost" icon={<RotateCcw className="size-4" />} onClick={wc.resetToDraft} disabled={!wc.dirtyVsServer && !card.working}>
                  Reset to draft
                </Button>
                <span className="ml-auto text-xs text-muted">Saved on this device · synced when you leave</span>
              </div>
              {showDiff && <DiffPanel before={baseline} after={text} />}
              <HooksPanel hooks={card.hooks ?? []} selected={wc.copy.hookIndex} onUse={useHook} />
            </>
          )}
          <div className="lg:hidden">{sidePanel}</div>
        </div>
        <aside className="hidden lg:block">
          <div className="sticky top-6 max-h-[calc(100dvh-3rem)] overflow-y-auto rounded-2xl border border-border bg-surface p-4">{sidePanel}</div>
        </aside>
      </div>

      {editable && (
        // On phones the bar sits directly on the bottom nav (a 3.5rem row plus the safe area).
        <div className="fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-20 border-t border-border bg-surface px-3 py-2 lg:static lg:mt-6 lg:rounded-2xl lg:border lg:px-4 lg:py-3">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2">
            <Button variant="primary" icon={<Send className="size-4" />} onClick={() => setPosting(true)} disabled={!text.trim() || !!card.work}>
              Posted
            </Button>
            <Button icon={<Copy className="size-4" />} onClick={() => void copyAll()} disabled={!text.trim()}>
              Copy
            </Button>
            <LinkButton href={composeUrl} target="_blank" rel="noreferrer" icon={<ExternalLink className="size-4" />} className={cx(!text.trim() && "pointer-events-none opacity-50")}>
              Open {card.platform === "x" ? "X" : "LinkedIn"}
            </LinkButton>
            <Button variant="ghost" onClick={() => setRewriting(true)} disabled={!!card.work}>
              Rewrite
            </Button>
            <span className="ml-auto">
              <SkipMenu card={card} size="md" />
            </span>
          </div>
          {card.format === "x_thread" && <p className="mx-auto mt-1 max-w-6xl text-xs text-muted">Open X posts the first post; add the rest as replies to it, using each post's copy button.</p>}
        </div>
      )}

      {editable && <div aria-hidden className="h-28 lg:hidden" />}

      <PostedDialog
        open={posting}
        onClose={() => setPosting(false)}
        card={card}
        text={text}
        posts={wc.copy.posts}
        baseline={baseline}
        editingSeconds={seconds}
        onConfirm={confirmPosted}
      />
      <RewriteDialog open={rewriting} onClose={() => setRewriting(false)} card={card} onConfirm={confirmRewrite} />
    </div>
  );
}

function PostedSummary({ card, post, tz }: { card: Card; post: import("@/types").Post | undefined; tz: string }) {
  const url = safeUrl(post?.post_url);
  return (
    <Panel
      title="Posted"
      description={post ? `${formatDateTime(post.posted_at, tz)}${post.edit_ratio != null ? ` · edit ratio ${pct(post.edit_ratio)}` : ""}` : undefined}
      actions={
        <>
          {url && (
            <LinkButton size="sm" href={url} target="_blank" rel="noreferrer" icon={<ExternalLink className="size-4" />}>
              View post
            </LinkButton>
          )}
          <Link to={`/metrics?post=${post?.id ?? ""}`}>
            <Button size="sm">Add numbers</Button>
          </Link>
        </>
      }
    >
      <p className="draft-text text-[14.5px]">{post?.final_text ?? draftText(card)}</p>
    </Panel>
  );
}
