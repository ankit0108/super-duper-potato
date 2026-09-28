import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Card, Hook, Visual } from "@/types";
import { readJSON, remove, writeJSON } from "@/lib/storage";

export type WorkingCopy = {
  text: string;
  posts: string[];
  hookIndex: number | null;
  hooks: Hook[] | null; // the openings as edited here; null = the drafter's, untouched
  hashtags: string[] | null; // the hashtags he kept or added; null = the suggested ones
  visual: Visual | null; // the visual's text as edited here; null = the card's visual, untouched
  visualBase: string | null; // which visual (its created_at) those edits belong to: a newer one replaces them
  baseKey: string; // which server version these edits started from
  baseText: string; // that version's text/posts, to tell whether Ankit changed anything
  basePosts: string[];
  updatedAt: string;
};

const keyOf = (id: string) => `pbs.work.${id}`;

/** Identifies the server's current version of a card's text (a rewrite or another device changes it). */
export function draftKey(card: Card): string {
  const d = card.working ?? card.draft;
  const body = d ? (card.format === "x_thread" ? (d.posts ?? []).join("␞") : (d.text ?? "")) : "";
  return `${card.revision ?? 0}:${body.length}:${body.slice(0, 48)}`;
}

function fromCard(card: Card): WorkingCopy {
  const src = card.working ?? card.draft;
  const posts = card.format === "x_thread" ? (src?.posts?.length ? [...src.posts] : [""]) : [];
  const text = src?.text ?? "";
  return {
    text,
    posts,
    hookIndex: card.working?.hook_index ?? null,
    hooks: card.working?.hooks?.length ? card.working.hooks.map((h) => ({ type: h.type ?? "observation", text: h.text })) : null,
    hashtags: card.working?.hashtags ?? null,
    visual: card.working?.visual ?? null,
    visualBase: card.working?.visual?.created_at ?? null,
    baseKey: draftKey(card),
    baseText: text,
    basePosts: posts,
    updatedAt: card.working?.updated_at ?? card.updated_at ?? card.created_at,
  };
}

const same = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i]);
const visualKey = (v: Visual | null | undefined) =>
  v ? JSON.stringify([v.kind, v.title ?? "", v.subtitle ?? "", (v.items ?? []).map((it) => [it.title ?? "", it.body ?? ""]), v.caption ?? "", v.alt_text ?? ""]) : "";

/** His edits of the card's current visual, or null (none, or they belong to a visual that has been replaced). */
export function editedVisual(copy: WorkingCopy, card: Card): Visual | null {
  return copy.visual && card.visual?.created_at && copy.visualBase === card.visual.created_at ? copy.visual : null;
}

/** The visual to show: his edits here, else his synced edits, else the card's. */
export function currentVisual(copy: WorkingCopy, card: Card): Visual | null {
  const synced = card.working?.visual && card.working.visual.created_at === card.visual?.created_at ? card.working.visual : null;
  return editedVisual(copy, card) ?? synced ?? card.visual ?? null;
}
const sameHooks = (a: Hook[] | null | undefined, b: Hook[] | null | undefined) =>
  (a ?? []).length === (b ?? []).length && (a ?? []).every((h, i) => h.text === b![i].text);

export function useWorkingCopy(card: Card) {
  const [copy, setCopy] = useState<WorkingCopy>(() => {
    const saved = readJSON<WorkingCopy | null>(keyOf(card.id), null);
    return saved ? { ...saved, hooks: saved.hooks ?? null, hashtags: saved.hashtags ?? null, visual: saved.visual ?? null, visualBase: saved.visualBase ?? null } : fromCard(card);
  });
  const [newDraft, setNewDraft] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentKey = draftKey(card);

  // A rewrite (or an edit from another device) produced a new server version.
  useEffect(() => {
    if (copy.baseKey === currentKey) return;
    const server = fromCard(card);
    if (copy.text === server.text && same(copy.posts, server.posts)) {
      // The server caught up with our own edits: nothing to reconcile.
      setCopy((prev) => ({ ...prev, baseKey: server.baseKey, baseText: server.baseText, basePosts: server.basePosts }));
      return;
    }
    const untouched = copy.text === copy.baseText && same(copy.posts, copy.basePosts);
    if (untouched) {
      remove(keyOf(card.id));
      setCopy(fromCard(card));
    } else {
      setNewDraft(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentKey]);

  useEffect(
    () => () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    },
    [],
  );

  const update = useCallback(
    (patch: Partial<WorkingCopy>) => {
      setCopy((prev) => {
        const next = { ...prev, ...patch, updatedAt: new Date().toISOString() };
        if (saveTimer.current) clearTimeout(saveTimer.current);
        saveTimer.current = setTimeout(() => writeJSON(keyOf(card.id), next), 250);
        return next;
      });
    },
    [card.id],
  );

  const acceptNewDraft = useCallback(() => {
    remove(keyOf(card.id));
    setCopy(fromCard(card));
    setNewDraft(false);
  }, [card]);

  const keepMine = useCallback(() => {
    setNewDraft(false);
    const server = fromCard(card);
    update({ baseKey: server.baseKey, baseText: server.baseText, basePosts: server.basePosts });
  }, [card, update]);

  const resetToDraft = useCallback(() => {
    remove(keyOf(card.id));
    setCopy(fromCard({ ...card, working: null }));
  }, [card]);

  const clear = useCallback(() => remove(keyOf(card.id)), [card.id]);

  const finalText = useMemo(
    () => (card.format === "x_thread" ? copy.posts.filter((p) => p.trim()).join("\n\n") : copy.text),
    [copy, card.format],
  );

  /** Differs from what the server last saw (so a card.edit event is worth sending). */
  const dirtyVsServer = useMemo(() => {
    const server = fromCard(card);
    return (
      copy.text !== server.text ||
      !same(copy.posts, server.posts) ||
      copy.hookIndex !== server.hookIndex ||
      !sameHooks(copy.hooks, server.hooks) ||
      !same(copy.hashtags ?? [], server.hashtags ?? []) ||
      (copy.hashtags == null) !== (server.hashtags == null) ||
      (!!editedVisual(copy, card) && visualKey(editedVisual(copy, card)) !== visualKey(server.visual))
    );
  }, [copy, card]);

  return { copy, update, newDraft, acceptNewDraft, keepMine, resetToDraft, clear, finalText, dirtyVsServer };
}
