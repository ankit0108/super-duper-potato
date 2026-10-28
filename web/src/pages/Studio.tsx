import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Copy, FileText, Loader2, MessageSquarePlus, MessagesSquare, RotateCcw, Search, Sparkles, Trash2, TriangleAlert } from "lucide-react";
import type { Card } from "@/types";
import { parseReply, type StudioPost, type StudioVisual } from "@/lib/studio/blocks";
import { deleteChat, getChat, listChats, saveChat, titleFrom, type StudioChat, type StudioContext, type StudioImage, type StudioMessage } from "@/lib/studio/chats";
import { demoStream } from "@/lib/studio/demo";
import { listModels, StudioError, streamWithFallback } from "@/lib/studio/gemini";
import { contentsFor, evidenceOf, quickActions, systemFor, STARTERS, type QuickAction } from "@/lib/studio/prompt";
import { cachedModels, getStudioKey, setStudioKey } from "@/lib/studio/settings";
import { sharedContext, takeShared } from "@/lib/studio/shared";
import { prepImage, MAX_IMAGES } from "@/lib/studio/images";
import { copyText } from "@/lib/compose";
import { draftText, PLATFORM_LABEL, FORMAT_LABEL } from "@/lib/format";
import { Link, navigate, useRoute } from "@/lib/router";
import { newId } from "@/lib/storage";
import { relative } from "@/lib/time";
import { useDesk } from "@/state/store";
import { useNow } from "@/state/hooks";
import { Markdown } from "@/components/Markdown";
import { Button, IconButton, cx } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Panel } from "@/components/ui/Feedback";
import { VISUAL_LABEL } from "@/components/VisualViewer";
import { BrokenBlock, IdeasBlock, VisualBlock } from "./studio/Blocks";
import { Composer, type ComposerHandle } from "./studio/Composer";
import { useStudioEnv, type StudioEnv } from "./studio/env";
import { StudioKeyPanel } from "./studio/KeyPanel";
import { PostBlock, type VisualChoice } from "./studio/PostBlock";

const iso = () => new Date().toISOString();
const FIRST_PERSON = /\b(I|I'm|I've|I'd|me|my|mine|we|we're|our|us)\b/;

/** A card from the board, as what a Studio message is about. */
function cardContext(card: Card): StudioContext {
  const sources = (card.sources ?? []).slice(0, 6).map((s) => `- ${s.title ?? s.url}${s.url ? ` (${s.url})` : ""}`);
  return {
    kind: "card",
    card_id: card.id,
    title: card.title,
    body: [
      `A post from my board (${PLATFORM_LABEL[card.platform]}, ${FORMAT_LABEL[card.format]}): ${card.title}`,
      card.why_now ? `Why now: ${card.why_now}` : "",
      card.angle ? `Angle: ${card.angle}` : "",
      draftText(card) ? `The draft:\n${card.working?.text || draftText(card)}` : "",
      sources.length ? `Sources:\n${sources.join("\n")}` : "",
    ]
      .filter(Boolean)
      .join("\n\n"),
  };
}

/** Pictures you shared (not screenshots of someone else's post) up to a message, newest last. */
function ownPictures(messages: StudioMessage[], upTo: number): StudioImage[] {
  return messages.slice(0, upTo).flatMap((m) => (m.role === "user" && m.context?.kind !== "shared" ? (m.images ?? []) : []));
}

/** The Studio: a chat that researches, looks at your pictures and writes posts and carousels in your voice. */
export function Studio() {
  const route = useRoute();
  const env = useStudioEnv();
  const demo = useDesk((s) => s.connection?.mode === "demo");
  const view = useDesk((s) => s.view);
  const [chats, setChats] = useState<StudioChat[]>([]);
  const [chat, setChat] = useState<StudioChat | null>(null);
  const chatRef = useRef<StudioChat | null>(null);
  const [key, setKey] = useState(getStudioKey);
  const [streaming, setStreaming] = useState<{ id: string; model: string } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [draft, setDraft] = useState("");
  const [images, setImages] = useState<StudioImage[]>([]);
  const [context, setContext] = useState<StudioContext | null>(null);
  const [listOpen, setListOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const composer = useRef<ComposerHandle>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const ready = demo || !!key;
  const routeId = route.parts[1] ? decodeURIComponent(route.parts[1]) : null;

  const refreshList = useCallback(() => void listChats().then(setChats), []);
  useEffect(refreshList, [refreshList]);

  /** Show a chat (null: a new one); `persist` also writes it to this device. */
  const commit = useCallback((c: StudioChat | null, persist = true) => {
    chatRef.current = c;
    setChat(c);
    if (c && persist) void saveChat(c);
  }, []);
  const patchMessage = useCallback(
    (id: string, patch: Partial<StudioMessage>, persist = false) => {
      const c = chatRef.current;
      if (!c) return;
      commit({ ...c, updated_at: persist ? iso() : c.updated_at, messages: c.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)) }, persist);
    },
    [commit],
  );

  // The chat in the address (#/studio/<id>), or a new one.
  useEffect(() => {
    if (routeId === (chatRef.current?.id ?? null)) return;
    abortRef.current?.abort();
    if (!routeId) return commit(null, false);
    void getChat(routeId).then((c) => (c ? commit(c, false) : navigate("/studio", { replace: true })));
  }, [routeId, commit]);

  // Arriving with something to talk about: a card (Ask Studio) or a post shared from another app.
  const cardParam = route.query.get("card");
  const sharedParam = route.query.get("shared");
  useEffect(() => {
    if (cardParam) {
      const card = view?.cards?.find((c) => c.id === cardParam);
      if (card) setContext(cardContext(card));
      navigate("/studio", { replace: true });
    }
  }, [cardParam, view]);
  useEffect(() => {
    if (!sharedParam) return;
    void (async () => {
      const shared = await takeShared();
      navigate("/studio", { replace: true });
      if (!shared) return;
      setContext({ kind: "shared", ...sharedContext(shared) });
      const pics: StudioImage[] = [];
      for (const f of shared.files.slice(0, MAX_IMAGES)) {
        try {
          pics.push(await prepImage(f, "shared.jpg"));
        } catch {
          /* not a picture this browser can read */
        }
      }
      setImages(pics);
    })();
  }, [sharedParam]);

  // Follow the reply as it streams, unless you've scrolled up to read.
  const lastText = chat?.messages[chat.messages.length - 1]?.text.length ?? 0;
  const count = chat?.messages.length ?? 0;
  useEffect(() => {
    const nearBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 280;
    if (nearBottom || !streaming) bottom.current?.scrollIntoView({ block: "end" });
  }, [count, lastText, streaming]);

  const models = async (): Promise<string[]> => {
    const cached = cachedModels(key);
    if (cached) return cached;
    const found = await listModels(key);
    setStudioKey(key, found);
    return found;
  };

  const run = async (base: StudioChat) => {
    const reply: StudioMessage = { id: newId("msg"), role: "assistant", text: "", at: iso() };
    const lastUser = [...base.messages].reverse().find((m) => m.role === "user");
    commit({ ...base, updated_at: iso(), messages: [...base.messages, reply] });
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming({ id: reply.id, model: demo ? "demo" : "" });
    let latest = "";
    const onText = (t: string) => {
      latest = t;
      if (chatRef.current?.id === base.id) patchMessage(reply.id, { text: t });
    };
    // The reply's end state, saved to its chat even if you've moved to another one meanwhile.
    const finish = (patch: Partial<StudioMessage>) => {
      if (chatRef.current?.id === base.id) return patchMessage(reply.id, patch, true);
      void getChat(base.id).then((c) => c && saveChat({ ...c, messages: c.messages.map((m) => (m.id === reply.id ? { ...m, text: latest, ...patch } : m)) }));
    };
    try {
      const result = demo
        ? await demoStream({ ask: lastUser?.text ?? "", picture: !!lastUser?.images?.length, shared: base.messages.some((m) => m.context?.kind === "shared"), signal: ctrl.signal, onText })
        : await streamWithFallback({
            key,
            models: await models(),
            system: systemFor(env.kit, env.name, env.tz),
            contents: contentsFor(base, env.guardTerms),
            search: true,
            signal: ctrl.signal,
            onText,
            onModel: (m) => setStreaming({ id: reply.id, model: m }),
          });
      finish({ text: result.text, model: result.model, sources: result.sources, searched: result.searched });
    } catch (e) {
      if ((e as Error)?.name === "AbortError") finish({ stopped: true });
      else {
        const err = e instanceof StudioError ? e : new StudioError("Something went wrong talking to Gemini. Try again.", "network");
        finish({ error: err.message, error_kind: err.kind });
      }
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setStreaming((s) => (s?.id === reply.id ? null : s));
      refreshList();
    }
  };

  const send = (textIn?: string) => {
    const text = (textIn ?? draft).trim();
    if (streaming || !ready || (!text && !images.length && !context)) return;
    const now = iso();
    const user: StudioMessage = { id: newId("msg"), role: "user", text, at: now, ...(images.length ? { images } : {}), ...(context ? { context } : {}) };
    const base: StudioChat = chatRef.current ?? { id: newId("chat"), title: titleFrom(text || context?.title || "Pictures"), created_at: now, updated_at: now, messages: [] };
    const next = { ...base, updated_at: now, messages: [...base.messages, user] };
    setDraft("");
    setImages([]);
    setContext(null);
    void run(next);
    if (routeId !== next.id) navigate(`/studio/${encodeURIComponent(next.id)}`, { replace: !routeId });
  };
  const retry = (replyId: string) => {
    const c = chatRef.current;
    if (!c || streaming) return;
    const at = c.messages.findIndex((m) => m.id === replyId);
    if (at > 0) void run({ ...c, messages: c.messages.slice(0, at) });
  };
  const stop = () => abortRef.current?.abort();
  const newChat = () => {
    abortRef.current?.abort();
    setListOpen(false);
    commit(null, false);
    navigate("/studio");
    setTimeout(() => composer.current?.focus(), 0);
  };
  const removeChat = async (id: string) => {
    if (!window.confirm("Delete this chat from this device?")) return;
    await deleteChat(id);
    if (chatRef.current?.id === id) newChat();
    refreshList();
  };

  const messages = chat?.messages ?? [];
  const lastPost = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role !== "assistant") continue;
      const seg = [...parseReply(m.text)].reverse().find((s) => s.kind === "post");
      if (seg?.kind === "post") return seg.post;
    }
    return null;
  }, [messages]);
  const hasShared = !!context && context.kind === "shared" ? true : messages.some((m) => m.context?.kind === "shared") && !lastPost;
  const chips = quickActions({ hasPost: !!lastPost, platform: lastPost?.platform ?? null, shared: hasShared, card: context?.kind === "card" });
  const onChip = (a: QuickAction) => {
    const typed = draft.trim();
    if (typed || images.length || context || messages.length) return send(typed ? `${a.prompt}\n\n${typed}` : a.prompt);
    setDraft(a.start ?? a.prompt);
    composer.current?.focus();
  };

  const evidence = useMemo(() => (chat ? evidenceOf(chat) : ""), [chat]);
  const external = useMemo(() => !messages.some((m) => m.role === "user" && FIRST_PERSON.test(m.text)), [messages]);
  // Every visual in the chat (with your edits), for a post to be saved with.
  const visuals = useMemo(() => {
    const out: Array<VisualChoice & { message: number }> = [];
    messages.forEach((m, mi) => {
      if (m.role !== "assistant") return;
      parseReply(m.text).forEach((s, si) => {
        if (s.kind !== "visual") return;
        const v = m.visuals?.[si] ?? s.visual;
        const pics = ownPictures(messages, mi);
        out.push({ key: `${m.id}:${si}`, label: `${VISUAL_LABEL[v.kind]}: ${v.title || "untitled"}`, visual: v, photo: pics[pics.length - 1] ?? null, message: mi });
      });
    });
    return out;
  }, [messages]);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (!ready || streaming) return;
    void composer.current?.addFiles(Array.from(e.dataTransfer.files ?? []));
  };

  const list = <ChatList chats={chats} current={chat?.id ?? null} onNew={newChat} onDelete={(id) => void removeChat(id)} onOpen={() => setListOpen(false)} />;

  return (
    <div
      className="relative lg:grid lg:grid-cols-[15rem_1fr] lg:gap-6"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <aside className="hidden lg:block">
        <div className="sticky top-6">{list}</div>
      </aside>

      <div className="flex min-h-[calc(100dvh-10rem)] min-w-0 flex-col">
        <header className="mb-4 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <Sparkles className="size-5 text-accent" aria-hidden /> Studio
            </h1>
            <p className="truncate text-sm text-muted">{chat ? chat.title : "Ask anything, share a picture or a post, and write it up for LinkedIn or X."}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1 lg:hidden">
            <IconButton label="Chats" icon={<MessagesSquare className="size-5" />} onClick={() => setListOpen(true)} />
            <IconButton label="New chat" icon={<MessageSquarePlus className="size-5" />} onClick={newChat} />
          </div>
        </header>

        {!ready ? (
          <Panel title="Set up the Studio" description="One step: a free Gemini key, kept on this device.">
            <StudioKeyPanel compact onReady={() => setKey(getStudioKey())} />
          </Panel>
        ) : (
          <>
            {!env.kit && !demo && (
              <p className="mb-3 rounded-xl bg-info-soft px-3 py-2 text-[13px] text-info">The Studio writes best after the next pipeline run, which brings it your style, your platform guide and examples of your posts.</p>
            )}
            <div className="flex-1 space-y-5 pb-4">
              {messages.length === 0 ? (
                <Starters
                  hasInput={!!(draft.trim() || images.length || context)}
                  onPick={(a) => {
                    if (a.pick) {
                      setDraft(a.prompt);
                      composer.current?.pickImages();
                    } else if (a.start) {
                      setDraft(a.start);
                      composer.current?.focus();
                    } else send(a.prompt);
                  }}
                />
              ) : (
                messages.map((m, i) =>
                  m.role === "user" ? (
                    <UserMessage key={m.id} message={m} />
                  ) : (
                    <AssistantMessage
                      key={m.id}
                      message={m}
                      index={i}
                      messages={messages}
                      env={env}
                      streaming={streaming?.id === m.id ? streaming : null}
                      busy={!!streaming}
                      last={i === messages.length - 1}
                      evidence={evidence}
                      external={external}
                      visuals={visuals}
                      onAsk={(p) => send(p)}
                      onRetry={() => retry(m.id)}
                      onPatch={(patch) => patchMessage(m.id, patch, true)}
                    />
                  ),
                )
              )}
              <div ref={bottom} />
            </div>
            <div className="sticky bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-20 -mx-4 bg-bg/95 px-4 pt-2 pb-2 backdrop-blur lg:bottom-0 lg:mx-0 lg:px-0 lg:pb-4">
              <Composer
                ref={composer}
                value={draft}
                onChange={setDraft}
                images={images}
                onImages={setImages}
                context={context}
                onClearContext={() => setContext(null)}
                chips={chips}
                onChip={onChip}
                onSend={() => send()}
                onStop={stop}
                streaming={!!streaming}
              />
            </div>
          </>
        )}
      </div>

      {dragging && ready && (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-accent/10 backdrop-blur-[1px]">
          <p className="rounded-2xl bg-surface px-5 py-3 text-sm font-medium shadow-lg">Drop pictures to add them</p>
        </div>
      )}
      <Dialog open={listOpen} onClose={() => setListOpen(false)} title="Chats">
        {list}
      </Dialog>
    </div>
  );
}

function ChatList({ chats, current, onNew, onDelete, onOpen }: { chats: StudioChat[]; current: string | null; onNew: () => void; onDelete: (id: string) => void; onOpen: () => void }) {
  const now = useNow(60_000);
  return (
    <nav aria-label="Studio chats" className="space-y-2">
      <Button variant="primary" icon={<MessageSquarePlus className="size-4" />} onClick={onNew} className="w-full">
        New chat
      </Button>
      {chats.length === 0 ? (
        <p className="px-1 text-[13px] text-muted">Your chats stay on this device.</p>
      ) : (
        <ul className="space-y-0.5">
          {chats.map((c) => (
            <li key={c.id} className={cx("group flex items-center gap-1 rounded-lg pr-1", c.id === current ? "bg-accent-soft" : "hover:bg-surface-2")}>
              <Link to={`/studio/${encodeURIComponent(c.id)}`} onClick={onOpen} aria-current={c.id === current ? "page" : undefined} className="min-w-0 flex-1 px-2.5 py-2">
                <span className={cx("block truncate text-[13.5px] font-medium", c.id === current && "text-accent")}>{c.title}</span>
                <span className="block text-[11.5px] text-muted">{relative(c.updated_at, now)}</span>
              </Link>
              <IconButton size="sm" label={`Delete “${c.title}”`} icon={<Trash2 className="size-4" />} onClick={() => onDelete(c.id)} className="opacity-60 group-hover:opacity-100" />
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}

function Starters({ onPick, hasInput }: { onPick: (a: QuickAction) => void; hasInput: boolean }) {
  return (
    <div className="py-6 text-center sm:py-10">
      <p className="text-lg font-semibold">What do you want to post about?</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted">Ask about anything, drop in a photo or a screenshot of a post you liked, or start from one of these. It searches the web when it needs to and writes in your voice.</p>
      {!hasInput && (
        <div className="mx-auto mt-5 grid max-w-xl gap-2 sm:grid-cols-2">
          {STARTERS.map((s) => (
            <button key={s.label} type="button" onClick={() => onPick(s)} className="rounded-xl border border-border bg-surface px-3 py-2.5 text-left text-[13.5px] hover:border-accent">
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ContextChip({ context }: { context: StudioContext }) {
  return (
    <details className="rounded-xl border border-border bg-surface px-3 py-2 text-left text-[13px]">
      <summary className="flex cursor-pointer items-center gap-1.5 font-medium">
        <FileText className="size-4 text-muted" aria-hidden /> {context.kind === "card" ? "Card" : "Shared"}: {context.title}
      </summary>
      <p className="mt-1.5 text-[12.5px] whitespace-pre-wrap text-muted">{context.body}</p>
      {context.card_id && (
        <Link to={`/card/${context.card_id}`} className="mt-1 inline-block text-[12.5px] text-accent hover:underline">
          Open the card
        </Link>
      )}
    </details>
  );
}

function UserMessage({ message }: { message: StudioMessage }) {
  const [big, setBig] = useState<string | null>(null);
  return (
    <div className="ml-auto flex max-w-[88%] flex-col items-end gap-1.5 sm:max-w-[75%]">
      {message.context && <ContextChip context={message.context} />}
      {!!message.images?.length && (
        <div className="flex flex-wrap justify-end gap-1.5">
          {message.images.map((img, i) => (
            <button key={img.id} type="button" onClick={() => setBig(big === img.id ? null : img.id)} aria-label={`Picture ${i + 1}${big === img.id ? ", shown large" : ""}`}>
              <img src={img.dataUrl} alt="" className={cx("rounded-xl border border-border object-cover", big === img.id ? "max-h-96 w-auto" : "size-24")} />
            </button>
          ))}
        </div>
      )}
      {message.text && <div className="rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-[14.5px] whitespace-pre-wrap text-accent-fg">{message.text}</div>}
    </div>
  );
}

function AssistantMessage({
  message,
  index,
  messages,
  env,
  streaming,
  busy,
  last,
  evidence,
  external,
  visuals,
  onAsk,
  onRetry,
  onPatch,
}: {
  message: StudioMessage;
  index: number;
  messages: StudioMessage[];
  env: StudioEnv;
  streaming: { id: string; model: string } | null;
  busy: boolean;
  last: boolean;
  evidence: string;
  external: boolean;
  visuals: Array<VisualChoice & { message: number }>;
  onAsk: (prompt: string) => void;
  onRetry: () => void;
  onPatch: (patch: Partial<StudioMessage>) => void;
}) {
  const toast = useDesk((s) => s.toast);
  const segments = useMemo(() => parseReply(message.text), [message.text]);
  const pics = useMemo(() => ownPictures(messages, index), [messages, index]);
  // The pictures from your latest message that had any: the default to post with a draft.
  const recentPictures = useMemo(() => {
    for (let i = index - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "user" && m.context?.kind !== "shared" && m.images?.length) return m.images.map((p) => p.id);
    }
    return [];
  }, [messages, index]);
  const prevAssistant = useMemo(() => {
    for (let i = index - 1; i >= 0; i--) if (messages[i].role === "assistant") return i;
    return -1;
  }, [messages, index]);
  const live = !!streaming;
  const copyReply = async () => {
    const ok = await copyText(message.text);
    toast(ok ? "ok" : "bad", ok ? "Reply copied." : "Couldn't copy.");
  };

  return (
    <div className="space-y-3">
      {live && !message.text && (
        <p className="flex items-center gap-2 text-[13.5px] text-muted" role="status">
          <Loader2 className="size-4 animate-spin text-accent" /> Thinking{streaming?.model && streaming.model !== "demo" ? ` (${streaming.model})` : ""}…
        </p>
      )}
      {segments.map((s, si) => {
        const k = `${message.id}:${si}`;
        if (s.kind === "text") return <Markdown key={k} text={s.text} className="text-[14.5px] leading-relaxed" />;
        if (s.kind === "pending")
          return (
            <div key={k} className="flex items-center gap-2 rounded-2xl border border-dashed border-border px-3 py-4 text-[13px] text-muted">
              <Loader2 className="size-4 animate-spin" /> {s.name === "visual" ? "Drawing up the visual…" : s.name === "ideas" ? "Listing ideas…" : "Writing the post…"}
            </div>
          );
        if (s.kind === "broken") return <BrokenBlock key={k} name={s.name === "visual" ? "visual" : s.name === "ideas" ? "list of ideas" : "post"} raw={s.raw} onRetry={onRetry} disabled={busy} />;
        if (s.kind === "ideas") return <IdeasBlock key={k} ideas={s.ideas} onAsk={onAsk} disabled={busy} />;
        if (s.kind === "visual") {
          const v = message.visuals?.[si] ?? s.visual;
          return <VisualBlock key={k} visual={v} env={env} photo={pics[pics.length - 1] ?? null} onAsk={onAsk} disabled={busy} onChange={(nv: StudioVisual) => onPatch({ visuals: { ...message.visuals, [si]: nv } })} />;
        }
        const post = message.posts?.[si] ?? s.post;
        const sameMessage = visuals.find((v) => v.key.startsWith(`${message.id}:`) && v.visual.platform === post.platform);
        const previous = visuals.filter((v) => v.message === prevAssistant).pop();
        return (
          <PostBlock
            key={k}
            original={s.post}
            post={post}
            onChange={(p: StudioPost) => onPatch({ posts: { ...message.posts, [si]: p } })}
            env={env}
            pictures={pics}
            defaultPictures={recentPictures}
            visuals={visuals}
            defaultVisual={(sameMessage ?? previous)?.key ?? null}
            evidence={evidence}
            external={external}
            model={message.model ?? null}
            savedCardId={message.saved?.[si]}
            onSaved={(id) => onPatch({ saved: { ...message.saved, [si]: id } })}
          />
        );
      })}
      {message.stopped && <p className="text-[12.5px] text-muted">Stopped.</p>}
      {message.error && (
        <div className="space-y-2 rounded-xl border border-bad/30 bg-bad-soft px-3 py-2 text-[13.5px]" role="alert">
          <p className="flex items-start gap-1.5 text-bad">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> {message.error}
          </p>
          {message.error_kind === "key" && (
            <p className="text-[12.5px]">
              Check the key in{" "}
              <Link to="/settings" className="text-accent hover:underline">
                Settings → Studio
              </Link>
              .
            </p>
          )}
          {message.error_kind === "quota" && <p className="text-[12.5px] text-muted">The free quota resets daily. A key from a second Google Cloud project doubles it (Settings → Studio).</p>}
          {last && (
            <Button size="sm" icon={<RotateCcw className="size-4" />} onClick={onRetry} disabled={busy}>
              Try again
            </Button>
          )}
        </div>
      )}
      {!live && !message.error && message.text && (
        <div className="space-y-1.5">
          {!!message.sources?.length && (
            <div className="flex flex-wrap gap-1.5" aria-label="Sources">
              {message.sources.slice(0, 8).map((s) => (
                <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="max-w-[16rem] truncate rounded-full border border-border px-2.5 py-1 text-[12px] text-muted hover:border-accent hover:text-accent">
                  {s.title}
                </a>
              ))}
            </div>
          )}
          <div className="flex items-center gap-1 text-[11.5px] text-faint">
            {!!message.searched?.length && (
              <span className="mr-1 inline-flex min-w-0 items-center gap-1 truncate" title={message.searched.join(" · ")}>
                <Search className="size-3 shrink-0" aria-hidden /> Searched: {message.searched.slice(0, 2).join(" · ")}
              </span>
            )}
            {message.model && message.model !== "demo" && <span className="mr-auto truncate">{message.model}</span>}
            <IconButton size="sm" label="Copy reply" icon={<Copy className="size-3.5" />} onClick={() => void copyReply()} className="ml-auto" />
            {last && <IconButton size="sm" label="Write it again" icon={<RotateCcw className="size-3.5" />} onClick={onRetry} disabled={busy} />}
          </div>
        </div>
      )}
    </div>
  );
}
