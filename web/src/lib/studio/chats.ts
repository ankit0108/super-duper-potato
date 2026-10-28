// Studio chats live on this device only (IndexedDB, with an in-memory fallback where it's unavailable): nothing is
// sent anywhere except to Gemini while you chat, and to the data repo when you save a post to the board.

import type { Source } from "./gemini";
import type { StudioPost, StudioVisual } from "./blocks";

export type StudioImage = { id: string; mime: string; width: number; height: number; dataUrl: string; name?: string };
/** What a message is about besides its text: a card from the board, or a post shared from another app. */
export type StudioContext = { kind: "card" | "shared"; title: string; body: string; card_id?: string };

export type StudioMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  at: string;
  images?: StudioImage[];
  context?: StudioContext;
  model?: string;
  sources?: Source[];
  searched?: string[];
  error?: string;
  error_kind?: string;
  /** You stopped the reply before it finished. */
  stopped?: boolean;
  /** Your edits to the blocks in this reply, by block index. */
  posts?: Record<number, StudioPost>;
  visuals?: Record<number, StudioVisual>;
  /** Blocks you saved to the board: block index -> card id. */
  saved?: Record<number, string>;
};

export type StudioChat = { id: string; title: string; created_at: string; updated_at: string; messages: StudioMessage[] };

const DB = "pbs-studio";
const STORE = "chats";
const memory = new Map<string, StudioChat>();

function open(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id" });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T | undefined> {
  const db = await open();
  if (!db) return undefined;
  return new Promise((resolve) => {
    try {
      const req = fn(db.transaction(STORE, mode).objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(undefined);
    } catch {
      resolve(undefined);
    }
  });
}

export async function listChats(): Promise<StudioChat[]> {
  const rows = (await tx<StudioChat[]>("readonly", (s) => s.getAll() as IDBRequest<StudioChat[]>)) ?? [...memory.values()];
  return [...rows].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export async function getChat(id: string): Promise<StudioChat | null> {
  return (await tx<StudioChat>("readonly", (s) => s.get(id) as IDBRequest<StudioChat>)) ?? memory.get(id) ?? null;
}

export async function saveChat(chat: StudioChat): Promise<void> {
  memory.set(chat.id, chat);
  await tx("readwrite", (s) => s.put(chat));
}

export async function deleteChat(id: string): Promise<void> {
  memory.delete(id);
  await tx("readwrite", (s) => s.delete(id));
}

/** A chat's title: the first thing you asked, shortened. */
export function titleFrom(text: string): string {
  const line = text.replace(/\s+/g, " ").trim();
  return line.length > 60 ? `${line.slice(0, 57).replace(/\s+\S*$/, "")}…` : line || "New chat";
}
