import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowLeftRight, ChevronDown, Copy, ExternalLink, GitCompare, Loader2, MessageCircleQuestion, RotateCcw, Send, Sparkle, Undo2 } from "lucide-react";
import type { Card, EventInput } from "@/types";
import { FORMAT_LABEL, PLATFORM_LABEL, SKIP_REASONS, draftText, pct } from "@/lib/format";
import { copyText, linkedInComposeUrl, safeUrl, xComposeUrl } from "@/lib/compose";
import { liveFlags, parseTerms } from "@/lib/guard";
import { withHashtags, withoutHashtags } from "@/lib/hashtags";
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
import { FlagIcons, SkipMenu, StillWaiting, workLabel } from "@/components/card/CardTile";
import { DiffPanel, HooksPanel, LinkedInEditor, LiveChecks, ThreadEditor, XPostEditor, numbered, replaceOpening, swapOpening } from "./card/Editor";
import { Details, PipelineFlags, ReplyHelper, Sources, WhyAngle } from "./card/Context";
import { CrosspostDialog, PostedDialog, RewriteDialog, type CrosspostPayload, type PostedPayload } from "./card/Dialogs";
import { FirstComment } from "./card/FirstComment";
import { HashtagsBar } from "./card/Hashtags";
import { Interview } from "./card/Interview";
import { currentVisual, editedVisual, useWorkingCopy, type WorkingCopy } from "./card/useWorkingCopy";
import { VISUAL_KINDS, VisualPanel, type VisualChoice } from "./card/VisualPanel";

/** The working copy as a card.edit event: text or thread posts, the opening in use and his edited openings. */
function editEvent(card: Card, copy: WorkingCopy): EventInput {
  return {
    type: "card.edit",
    card_id: card.id,
    ...(card.format === "x_thread" ? { posts: copy.posts } : { text: copy.text }),
    hook_index: copy.hookIndex,
    ...(copy.hooks ? { hooks: copy.hooks.map((h) => ({ type: h.type ?? "observation", text: h.text })) } : {}),
    ...(copy.hashtags ? { hashtags: copy.hashtags } : {}),
    ...visualIn(editedVisual(copy, card)),
  };
}

/** His edits of the visual, in the event's shape (only the words; the pipeline keeps its sources and checks). */
function visualIn(v: import("@/types").Visual | null) {
  if (!v) return {};
  return {
    visual: {
      kind: v.kind,
      title: v.title ?? "",
      subtitle: v.subtitle ?? null,
      items: (v.items ?? []).slice(0, 12).map((it) => ({ title: it.title ?? "", body: it.body ?? "" })),
      caption: v.caption ?? null,
      alt_text: v.alt_text ?? "",
    },
  };
}

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
  const [crossposting, setCrossposting] = useState(false);
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
  const body = wc.finalText; // what he's editing: the post without hashtags
  const suggestedTags = useMemo(() => card.hashtags ?? [], [card.hashtags]);
  const tagsOn = (view?.settings as { hashtags?: { enabled?: boolean } } | undefined)?.hashtags?.enabled !== false;
  const chosenTags = wc.copy.hashtags ?? suggestedTags;
  const tagLine = chosenTags.join(" ");
  // What goes out: the post with the chosen hashtags at the end (post 1 of a thread).
  const composed = withHashtags(card.format, { text: wc.copy.text, posts: wc.copy.posts }, chosenTags);
  const text = card.format === "x_thread" ? composed.posts.filter((p) => p.trim()).join("\n\n") : composed.text;
  // Anything not written from his own answers is analysis: experiences in it are flagged (as in the pipeline).
  const external = card.mode === "external" || card.draft_basis === "sources" || !(card.answers?.length ?? 0);
  const flags = useMemo(
    () =>
      liveFlags({
        text: body,
        evidence: evidenceFor(card),
        guardTerms,
        avoid,
        bait,
        external,
        platform: { platform: card.platform, format: card.format, hashtags: chosenTags.length, fold },
      }),
    [body, card, guardTerms, avoid, bait, external, chosenTags.length, fold],
  );
  const setTags = (tags: string[]) => {
    markEditing();
    wc.update({ hashtags: tags });
  };
  const visual = currentVisual(wc.copy, card);
  const visualBusy = card.work?.kind === "visual";
  const visualsOn = (settings?.visuals as { enabled?: boolean } | undefined)?.enabled !== false;
  const imageName =
    (card.platform === "linkedin" ? settings?.visuals?.name_linkedin : settings?.visuals?.name_x) || view?.meta?.display_name || settings?.display_name || "";
  const requestVisual = (kind: VisualChoice, note: string, aiBackground = false) => {
    markEditing(); // asking for a visual picks the card, like editing it
    const events: EventInput[] = [];
    // The visual is drawn from the text as he has it now.
    if (wc.dirtyVsServer) events.push(editEvent(card, wc.copy));
    events.push({ type: "card.visual", card_id: card.id, kind, note, ai_background: aiBackground && kind !== "image" });
    const label = VISUAL_KINDS.find((k) => k.value === kind)?.label;
    const what = kind === "auto" ? "a visual" : kind === "image" ? "an AI image" : `a ${label?.toLowerCase()}`;
    act(events, { toast: `Making ${what}${aiBackground && kind !== "image" ? " with an AI background" : ""} for this post. It arrives within 1–3 minutes.` });
  };
  const editVisual = (v: import("@/types").Visual) => {
    markEditing();
    wc.update({ visual: v, visualBase: card.visual?.created_at ?? null });
  };

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
      act(editEvent(c, w.copy));
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
  const hooks = wc.copy.hooks ?? card.hooks ?? [];
  const useHook = (i: number) => {
    const hook = hooks[i]?.text;
    if (!hook) return;
    markEditing();
    if (card.format === "x_thread") {
      const posts = [...wc.copy.posts];
      posts[0] = replaceOpening(posts[0] ?? "", hook);
      wc.update({ posts, hookIndex: i });
    } else {
      wc.update({ text: replaceOpening(wc.copy.text, hook), hookIndex: i });
    }
    act({ type: "card.hook", card_id: card.id, hook_index: i, text: hook });
  };
  const editHook = (i: number, text: string) => {
    const before = hooks[i]?.text ?? "";
    const next = hooks.map((h, j) => (j === i ? { ...h, text } : h));
    markEditing();
    if (wc.copy.hookIndex !== i) return wc.update({ hooks: next });
    // The opening in use changes in the draft too.
    if (card.format === "x_thread") {
      const posts = [...wc.copy.posts];
      posts[0] = swapOpening(posts[0] ?? "", before, text);
      wc.update({ hooks: next, posts });
    } else {
      wc.update({ hooks: next, text: swapOpening(wc.copy.text, before, text) });
    }
  };
  const addHook = (text: string) => {
    const next = [...hooks, { type: "custom", text }];
    const i = next.length - 1;
    markEditing();
    if (card.format === "x_thread") {
      const posts = [...wc.copy.posts];
      posts[0] = replaceOpening(posts[0] ?? "", text);
      wc.update({ hooks: next, posts, hookIndex: i });
    } else {
      wc.update({ hooks: next, text: replaceOpening(wc.copy.text, text), hookIndex: i });
    }
    act({ type: "card.hook", card_id: card.id, hook_index: i, text });
  };

  const copyAll = async () => {
    const ok = await copyText(card.format === "x_thread" ? numbered(composed.posts.filter((p) => p.trim())).join("\n\n") : text);
    toast(ok ? "ok" : "bad", ok ? "Copied. Paste it into the app, then come back and tap Posted." : "Couldn't copy. Select the text and copy it manually.");
  };
  const composeUrl =
    card.platform === "linkedin"
      ? linkedInComposeUrl(text)
      : xComposeUrl(card.format === "x_thread" ? (composed.posts[0] ?? "") : text, card.format === "x_quote" ? safeUrl(card.draft?.quote_url) : undefined);

  const confirmPosted = (p: PostedPayload) => {
    act(
      [
        // Edited openings reach the pipeline before the post, so it learns which one went out.
        ...(wc.dirtyVsServer ? [editEvent(card, wc.copy)] : []),
        {
        type: "card.posted",
        card_id: card.id,
        ...(card.format === "x_thread" && p.posts ? { posts: p.posts } : { text: p.text }),
        post_url: p.post_url,
        posted_at: p.posted_at,
        editing_seconds: p.editing_seconds,
        hook_index: wc.copy.hookIndex,
        hashtags: chosenTags,
        with_visual: visual ? p.with_visual : null,
        },
      ],
      { toast: baseline ? `Posted. You changed ${pct(editRatio(baseline, withoutHashtags(p.text, chosenTags)))} of the draft.` : "Posted." },
    );
    wc.clear();
    setPosting(false);
    navigate("/");
  };

  const confirmRewrite = (r: { note: string; chips: string[]; target_platform?: Card["platform"]; target_format?: Card["format"] }) => {
    const events: EventInput[] = [];
    if (wc.dirtyVsServer) events.push(editEvent(card, wc.copy));
    if (r.target_platform && r.target_platform !== card.platform) {
      // Adapting for the other platform is a cross-post: this card stays, a new one is made and learned from.
      events.push({ type: "card.crosspost", card_id: card.id, target_platform: r.target_platform, target_format: r.target_format ?? null, mode: "both", note: r.note });
    } else {
      events.push({ type: "card.rewrite", card_id: card.id, note: r.note, chips: r.chips, target_platform: null, target_format: r.target_format ?? null });
    }
    act(events, { toast: r.target_platform ? `Making the ${PLATFORM_LABEL[r.target_platform]} version. It appears on the board within 1–3 minutes.` : "Rewrite requested. The new draft arrives within 1–3 minutes." });
    setRewriting(false);
  };
  const confirmCrosspost = (c: CrosspostPayload) => {
    const events: EventInput[] = [];
    if (wc.dirtyVsServer && editable) events.push(editEvent(card, wc.copy));
    events.push({ type: "card.crosspost", card_id: card.id, target_platform: c.target_platform, target_format: c.target_format, mode: c.mode, note: c.note });
    const other = PLATFORM_LABEL[c.target_platform];
    act(events, {
      toast: c.mode === "switch" ? `Moving it to ${other}: the new card appears within 1–3 minutes, and this one is skipped as the wrong platform.` : `Making the ${other} version. It appears on the board within 1–3 minutes.`,
    });
    setCrossposting(false);
    if (c.mode === "switch") navigate("/");
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
        <CrosspostLinks card={card} />
      </header>

      {work && (
        <div className="mb-4">
          <Banner tone="info">
            <span className="inline-flex items-center gap-2">
              <Loader2 className="size-4 animate-spin" /> {work} The pipeline is on it; this page updates by itself.
            </span>
            {card.work?.last_error && <span className="block text-xs text-muted">{card.work.last_error}</span>}
            <StillWaiting card={card} className="block" />
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
            <PostedSummary card={card} post={post} tz={tz} onCrosspost={() => setCrossposting(true)} />
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
                <LinkedInEditor value={wc.copy.text} onChange={setText} limit={liLimit} fold={fold} suffix={tagLine} />
              ) : card.format === "x_thread" ? (
                <ThreadEditor posts={wc.copy.posts} onChange={setPosts} limit={xLimit} min={threadMin} max={threadMax} firstSuffix={tagLine} />
              ) : (
                <XPostEditor value={wc.copy.text} onChange={setText} limit={xLimit} label={`${FORMAT_LABEL[card.format]} text`} minRows={5} suffix={tagLine} />
              )}
              {(suggestedTags.length > 0 || chosenTags.length > 0 || (tagsOn && card.format !== "x_reply")) && (
                <HashtagsBar platform={card.platform} suggested={suggestedTags} chosen={chosenTags} onChange={setTags} />
              )}
              {card.draft?.first_comment && <FirstComment platform={card.platform} text={card.draft.first_comment} />}
              {(visualsOn || visual) && (
                <VisualPanel
                  card={card}
                  visual={visual}
                  busy={visualBusy}
                  canRequest={visualsOn && (!card.work || visualBusy)}
                  name={imageName}
                  accent={settings?.visuals?.accent}
                  images={view?.images ?? null}
                  onRequest={requestVisual}
                  onEdit={editVisual}
                />
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
              {card.mode === "interview" && (card.questions?.length ?? 0) > 0 && <OptionalQuestions card={card} />}
              <HooksPanel hooks={hooks} selected={wc.copy.hookIndex} onUse={useHook} onEdit={editHook} onAdd={addHook} />
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
            <Button variant="primary" icon={<Send className="size-4" />} onClick={() => setPosting(true)} disabled={!text.trim() || (!!card.work && !visualBusy)}>
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
            <Button variant="ghost" icon={<ArrowLeftRight className="size-4" />} onClick={() => setCrossposting(true)} disabled={!!card.work}>
              {card.platform === "linkedin" ? "Also for X" : "Also for LinkedIn"}
            </Button>
            <span className="ml-auto">
              <SkipMenu card={card} size="md" side="top" />
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
        posts={composed.posts}
        tags={chosenTags}
        baseline={baseline}
        editingSeconds={seconds}
        visualLabel={visual ? VISUAL_KINDS.find((k) => k.value === visual.kind)?.label : null}
        onConfirm={confirmPosted}
      />
      <RewriteDialog open={rewriting} onClose={() => setRewriting(false)} card={card} onConfirm={confirmRewrite} />
      <CrosspostDialog open={crossposting} onClose={() => setCrossposting(false)} card={card} onConfirm={confirmCrosspost} />
    </div>
  );
}

/** "Cross-post of …" on a version made for the other platform, and links from the original to its versions. */
function CrosspostLinks({ card }: { card: Card }) {
  const cards = useDesk((s) => s.view?.cards);
  const original = card.crosspost_of ? cards?.find((c) => c.id === card.crosspost_of) : undefined;
  const versions = (cards ?? []).filter((c) => c.crosspost_of === card.id);
  if (!card.crosspost_of && !versions.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
      {card.crosspost_of && (
        <span className="inline-flex items-center gap-1">
          <ArrowLeftRight className="size-3.5" aria-hidden />
          {original ? (
            <>
              Cross-post of the {PLATFORM_LABEL[original.platform]} card{" "}
              <Link to={`/card/${original.id}`} className="font-medium text-accent hover:underline">
                {original.title}
              </Link>
            </>
          ) : (
            "Cross-post of a card from the other platform"
          )}
        </span>
      )}
      {versions.map((v) => (
        <span key={v.id} className="inline-flex items-center gap-1">
          <ArrowLeftRight className="size-3.5" aria-hidden />
          <Link to={`/card/${v.id}`} className="font-medium text-accent hover:underline">
            {PLATFORM_LABEL[v.platform]} version
          </Link>
          <span>({FORMAT_LABEL[v.format].toLowerCase()})</span>
        </span>
      ))}
    </div>
  );
}

/** A drafted card's questions, folded away: answering makes the post his own, but it's optional. */
function OptionalQuestions({ card }: { card: Card }) {
  const [open, setOpen] = useState(false);
  const n = card.questions?.length ?? 0;
  const answered = (card.answers?.length ?? 0) > 0;
  return (
    <div className="rounded-2xl border border-border bg-surface">
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
        <span className="flex items-center gap-2">
          <MessageCircleQuestion className="size-4 text-accent" aria-hidden />
          <span className="text-[14px] font-semibold">Make it yours</span>
          <span className="text-[13px] text-muted">
            · {n} optional question{n === 1 ? "" : "s"}
            {answered ? " · answered" : ""}
          </span>
        </span>
        <ChevronDown className={cx("size-4 text-muted transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className="border-t border-border p-4">
          <Interview card={card} />
        </div>
      )}
    </div>
  );
}

function PostedSummary({ card, post, tz, onCrosspost }: { card: Card; post: import("@/types").Post | undefined; tz: string; onCrosspost: () => void }) {
  const url = safeUrl(post?.post_url);
  return (
    <Panel
      title="Posted"
      description={post ? `${formatDateTime(post.posted_at, tz)}${post.edit_ratio != null ? ` · edit ratio ${pct(post.edit_ratio)}` : ""}` : undefined}
      actions={
        <>
          <Button size="sm" variant="ghost" icon={<ArrowLeftRight className="size-4" />} onClick={onCrosspost} disabled={!!card.work}>
            {card.platform === "linkedin" ? "Also for X" : "Also for LinkedIn"}
          </Button>
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
