import { create } from "zustand";
import type { Card, DeskState, EventInput, InboxBatch, InboxEvent, SkipReason } from "@/types";
import { processDemoEvents, loadDemoDesk } from "@/lib/demo";
import { GitHub, GitHubError, bytesToBase64, utf8ToBase64, type Connection, type WorkflowRun } from "@/lib/github";
import { applyEvents, emptyPending, type Pending } from "@/lib/overlay";
import { buildBatch, makeEvent, reconcile, toItem, type OutboxItem } from "@/lib/outbox";
import { newId, readJSON, remove, writeJSON } from "@/lib/storage";

export type RunState = "idle" | "queued" | "running" | "done" | "failed";
export type RunInfo = { state: RunState; requestedAt?: string; url?: string; startedAt?: string; conclusion?: string | null };
export type ToastTone = "info" | "ok" | "warn" | "bad";
export type Toast = { id: string; tone: ToastTone; text: string; actionLabel?: string; onAction?: () => void };
export type Prefs = { theme: "system" | "light" | "dark"; platform: "all" | "linkedin" | "x" };
/** The "why skip it?" dialog: open for one card, with a reason preselected. */
export type SkipPrompt = { cardId: string; reason: SkipReason } | null;

type Cache = { desk: DeskState; etag: string | null; fetchedAt: string };

const CONN_KEY = "pbs.connection";
const PREFS_KEY = "pbs.prefs";
const GUARD_KEY = "pbs.guardTerms";
const repoKey = (c: Connection | null) => (c && c.mode === "github" ? c.dataRepo : "demo");

let pollTimer: ReturnType<typeof setInterval> | null = null;
let runTimer: ReturnType<typeof setInterval> | null = null;
let dispatchTimer: ReturnType<typeof setTimeout> | null = null;
const remoteCache = new Map<string, InboxEvent[]>();

export type DeskStore = {
  connection: Connection | null;
  base: DeskState | null;
  etag: string | null;
  fetchedAt: string | null;
  loading: boolean;
  loadError: string | null;
  remoteEvents: InboxEvent[];
  outbox: OutboxItem[];
  flushing: boolean;
  online: boolean;
  run: RunInfo;
  workflowState: string | null;
  rateRemaining: number | null;
  view: DeskState | null;
  pending: Pending;
  toasts: Toast[];
  prefs: Prefs;
  guardTerms: string;
  skipPrompt: SkipPrompt;

  init: () => Promise<void>;
  connect: (conn: Connection) => Promise<void>;
  disconnect: () => void;
  refresh: (opts?: { quiet?: boolean }) => Promise<void>;
  act: (input: EventInput | EventInput[], opts?: { toast?: string }) => InboxEvent[];
  flush: () => Promise<void>;
  requestRun: (reason?: string) => void;
  dispatchNow: () => Promise<void>;
  uploadBlob: (path: string, bytes: Uint8Array) => Promise<void>;
  loadArchive: (month: string) => Promise<Card[]>;
  enableWorkflow: () => Promise<void>;
  checkWorkflow: () => Promise<void>;
  toast: (tone: ToastTone, text: string, action?: { label: string; onAction: () => void }) => void;
  dismissToast: (id: string) => void;
  setPrefs: (p: Partial<Prefs>) => void;
  setGuardTerms: (raw: string) => void;
  retryFailed: () => void;
  clearOutbox: () => void;
  askSkipReason: (cardId: string, reason: SkipReason) => void;
  closeSkipPrompt: () => void;
};

function gh(conn: Connection | null): GitHub | null {
  return conn && conn.mode === "github" ? new GitHub(conn) : null;
}

function recompute(state: Pick<DeskStore, "base" | "outbox" | "remoteEvents">): Pick<DeskStore, "view" | "pending"> {
  if (!state.base) return { view: null, pending: emptyPending() };
  const events = [...state.remoteEvents, ...state.outbox.map((i) => i.event)];
  const { desk, pending } = applyEvents(state.base, events);
  return { view: desk, pending };
}

export const useDesk = create<DeskStore>()((set, get) => {
  const setBase = (patch: Partial<DeskStore>) => {
    set(patch);
    set(recompute(get()));
  };
  const persistOutbox = () => writeJSON(`pbs.outbox.${repoKey(get().connection)}`, get().outbox);

  const applyReconcile = (desk: DeskState) => {
    const { items, rejected } = reconcile(get().outbox, desk);
    if (items.length !== get().outbox.length) {
      set({ outbox: items });
      persistOutbox();
    }
    for (const r of rejected) {
      get().toast("bad", `Couldn't apply "${r.item.event.type}": ${r.error}`);
    }
  };

  const startPolling = () => {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      if (typeof document === "undefined" || document.visibilityState === "visible") void get().refresh({ quiet: true });
    }, 60_000);
  };

  const trackRun = () => {
    if (runTimer) clearInterval(runTimer);
    const started = Date.now();
    runTimer = setInterval(async () => {
      const client = gh(get().connection);
      if (!client) return;
      if (Date.now() - started > 20 * 60_000) {
        clearInterval(runTimer!);
        set({ run: { state: "idle" } });
        return;
      }
      try {
        const runs = await client.latestRuns(5);
        const since = new Date(get().run.requestedAt ?? 0).getTime() - 60_000;
        const mine = runs.find((r: WorkflowRun) => new Date(r.created_at).getTime() >= since);
        if (!mine) return;
        if (mine.status === "completed") {
          clearInterval(runTimer!);
          const ok = mine.conclusion === "success";
          set({ run: { state: ok ? "done" : "failed", url: mine.html_url, conclusion: mine.conclusion } });
          await get().refresh({ quiet: true });
          if (!ok) get().toast("warn", "The pipeline run didn't finish cleanly. Details are on the System page.");
          setTimeout(() => get().run.state !== "queued" && set({ run: { state: "idle" } }), 8000);
        } else {
          set({ run: { ...get().run, state: mine.status === "in_progress" ? "running" : "queued", url: mine.html_url, startedAt: mine.run_started_at } });
        }
      } catch {
        /* keep polling */
      }
    }, 8000);
  };

  const fetchRemoteEvents = async (client: GitHub, device: string, processed: Set<string>) => {
    try {
      const files = (await client.listDir("inbox")).filter((f) => f.type === "file" && f.name.endsWith(".json"));
      const others = files.filter((f) => !f.name.includes(`_${device.slice(0, 16)}_`)).slice(-20);
      const events: InboxEvent[] = [];
      for (const f of others) {
        if (!remoteCache.has(f.sha)) {
          const res = await client.getRaw(f.path);
          try {
            const batch = JSON.parse(res.text ?? "{}") as InboxBatch;
            remoteCache.set(f.sha, (batch.events ?? []) as InboxEvent[]);
          } catch {
            remoteCache.set(f.sha, []);
          }
        }
        events.push(...(remoteCache.get(f.sha) ?? []).filter((e) => !processed.has(e.id)));
      }
      const own = new Set(get().outbox.map((i) => i.event.id));
      setBase({ remoteEvents: events.filter((e) => !own.has(e.id)) });
    } catch {
      /* optional: other devices' pending edits */
    }
  };

  return {
    connection: null,
    base: null,
    etag: null,
    fetchedAt: null,
    loading: false,
    loadError: null,
    remoteEvents: [],
    outbox: [],
    flushing: false,
    online: typeof navigator === "undefined" ? true : navigator.onLine,
    run: { state: "idle" },
    workflowState: null,
    rateRemaining: null,
    view: null,
    pending: emptyPending(),
    toasts: [],
    prefs: readJSON<Prefs>(PREFS_KEY, { theme: "system", platform: "all" }),
    guardTerms: readJSON<string>(GUARD_KEY, ""),
    skipPrompt: null,

    init: async () => {
      const conn = readJSON<Connection | null>(CONN_KEY, null);
      if (typeof window !== "undefined") {
        window.addEventListener("online", () => {
          set({ online: true });
          void get().flush();
          void get().refresh({ quiet: true });
        });
        window.addEventListener("offline", () => set({ online: false }));
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible" && get().connection) void get().refresh({ quiet: true });
        });
      }
      if (conn) await get().connect(conn);
    },

    connect: async (conn) => {
      writeJSON(CONN_KEY, conn);
      const cached = readJSON<Cache | null>(`pbs.cache.${repoKey(conn)}`, null);
      const outbox = readJSON<OutboxItem[]>(`pbs.outbox.${repoKey(conn)}`, []).map((i) =>
        i.state === "sending" ? { ...i, state: "pending" as const } : i,
      );
      setBase({
        connection: conn,
        base: cached?.desk ?? null,
        etag: cached?.etag ?? null,
        fetchedAt: cached?.fetchedAt ?? null,
        outbox,
        loadError: null,
        remoteEvents: [],
      });
      await get().refresh();
      void get().flush();
      if (conn.mode === "github") {
        startPolling();
        void get().checkWorkflow();
      }
    },

    disconnect: () => {
      if (pollTimer) clearInterval(pollTimer);
      if (runTimer) clearInterval(runTimer);
      const conn = get().connection;
      remove(CONN_KEY);
      if (conn) remove(`pbs.cache.${repoKey(conn)}`);
      setBase({ connection: null, base: null, etag: null, fetchedAt: null, outbox: [], remoteEvents: [], run: { state: "idle" } });
    },

    refresh: async (opts) => {
      const conn = get().connection;
      if (!conn) return;
      if (!opts?.quiet) set({ loading: true });
      try {
        if (conn.mode === "demo") {
          if (!get().base) {
            const desk = await loadDemoDesk();
            setBase({ base: desk, fetchedAt: new Date().toISOString(), loadError: null });
          }
          return;
        }
        const client = new GitHub(conn);
        const res = await client.getRaw("desk/desk.json", get().etag);
        set({ rateRemaining: client.rateRemaining, online: true });
        if (res.status === 404) {
          set({ loadError: "No desk.json yet. The first pipeline run creates it: use System → Run now, or wait for the schedule." });
          return;
        }
        if (res.status === 304) {
          set({ fetchedAt: new Date().toISOString(), loadError: null });
        } else if (res.text) {
          const desk = JSON.parse(res.text) as DeskState;
          if (!desk?.meta || (desk.meta.schema_version ?? 1) > 1) {
            set({ loadError: "This desk is older than the pipeline's data format. Reload the page to update it." });
          }
          const fetchedAt = new Date().toISOString();
          writeJSON(`pbs.cache.${repoKey(conn)}`, { desk, etag: res.etag, fetchedAt } satisfies Cache);
          setBase({ base: desk, etag: res.etag, fetchedAt, loadError: null });
          applyReconcile(desk);
        }
        const processed = new Set(get().base?.processed_event_ids ?? []);
        await fetchRemoteEvents(client, conn.device, processed);
      } catch (e) {
        const err = e as GitHubError;
        const msg =
          err.status === 401
            ? "GitHub rejected the token (expired or revoked). Update it in Settings → Connection."
            : err.status === 0
              ? "Offline: showing the last copy of your desk. Changes are saved on this device and sent when you're back online."
              : err.rateLimited
                ? "GitHub rate limit reached; the desk will retry shortly."
                : `Couldn't load the desk: ${err.message}`;
        set({ loadError: msg, online: err.status !== 0 });
      } finally {
        set({ loading: false });
      }
    },

    act: (input, opts) => {
      const inputs = Array.isArray(input) ? input : [input];
      const events = inputs.map((i) => makeEvent(i));
      let outbox = [...get().outbox];
      for (const ev of events) {
        if (ev.type === "card.edit") {
          // Coalesce: only the latest unsent edit per card matters.
          outbox = outbox.filter((i) => !(i.state === "pending" && i.event.type === "card.edit" && i.event.card_id === ev.card_id));
        }
        outbox.push(toItem(ev));
      }
      setBase({ outbox });
      persistOutbox();
      if (opts?.toast) get().toast("ok", opts.toast);
      void get().flush();
      return events;
    },

    flush: async () => {
      const conn = get().connection;
      if (!conn || get().flushing) return;
      const ready = get().outbox.filter((i) => i.state === "pending" || (i.state === "failed" && (i.attempts ?? 0) < 5));
      if (!ready.length) return;
      if (conn.mode === "demo") {
        const base = get().base;
        if (!base) return;
        await new Promise((r) => setTimeout(r, 350));
        const processed = processDemoEvents(base, ready.map((i) => i.event));
        const ids = new Set(ready.map((i) => i.event.id));
        setBase({ base: processed, outbox: get().outbox.filter((i) => !ids.has(i.event.id)) });
        persistOutbox();
        return;
      }
      if (!get().online) return;
      set({ flushing: true });
      const ids = new Set(ready.map((i) => i.event.id));
      set({ outbox: get().outbox.map((i) => (ids.has(i.event.id) ? { ...i, state: "sending" } : i)) });
      const { path, body } = buildBatch(ready.map((i) => i.event), conn.device);
      try {
        await new GitHub(conn).createFile(path, utf8ToBase64(JSON.stringify(body)), `desk: ${ready.length} event(s)`);
        const sentAt = new Date().toISOString();
        setBase({ outbox: get().outbox.map((i) => (ids.has(i.event.id) ? { ...i, state: "sent", batch: path, sentAt, error: undefined } : i)) });
        persistOutbox();
        if (ready.some((i) => i.needsRun)) get().requestRun();
      } catch (e) {
        const err = e as GitHubError;
        setBase({
          outbox: get().outbox.map((i) =>
            ids.has(i.event.id) ? { ...i, state: "failed", attempts: (i.attempts ?? 0) + 1, error: err.message } : i,
          ),
          online: err.status !== 0,
        });
        persistOutbox();
        if (err.status === 401 || err.status === 403) get().toast("bad", `Couldn't save your change: ${err.message}`);
      } finally {
        set({ flushing: false });
      }
      // Anything added while we were sending goes out next.
      if (get().outbox.some((i) => i.state === "pending")) void get().flush();
    },

    requestRun: () => {
      const conn = get().connection;
      if (!conn || conn.mode === "demo") return;
      set({ run: { state: "queued", requestedAt: new Date().toISOString() } });
      if (dispatchTimer) clearTimeout(dispatchTimer);
      dispatchTimer = setTimeout(() => void get().dispatchNow(), 4000);
    },

    dispatchNow: async () => {
      const conn = get().connection;
      if (!conn) return;
      if (conn.mode === "demo") {
        get().toast("info", "Demo mode: the pipeline isn't running, so changes are simulated.");
        return;
      }
      try {
        set({ run: { state: "queued", requestedAt: new Date().toISOString() } });
        await new GitHub(conn).dispatch();
        trackRun();
      } catch (e) {
        set({ run: { state: "failed" } });
        get().toast("bad", `Couldn't start the pipeline: ${(e as Error).message}`);
      }
    },

    uploadBlob: async (path, bytes) => {
      const conn = get().connection;
      if (!conn || conn.mode === "demo") return;
      await new GitHub(conn).createFile(path, bytesToBase64(bytes), "desk: analytics screenshot");
    },

    loadArchive: async (month) => {
      const conn = get().connection;
      if (!conn || conn.mode === "demo") return [];
      const res = await new GitHub(conn).getRaw(`db/cards/${month}.jsonl`);
      return (res.text ?? "")
        .split("\n")
        .filter(Boolean)
        .map((l) => JSON.parse(l) as Card);
    },

    checkWorkflow: async () => {
      const client = gh(get().connection);
      if (!client) return;
      try {
        set({ workflowState: await client.workflowState() });
      } catch {
        /* shown on the System page if it keeps failing */
      }
    },

    enableWorkflow: async () => {
      const client = gh(get().connection);
      if (!client) return;
      try {
        await client.enableWorkflow();
        set({ workflowState: "active" });
        get().toast("ok", "Schedule re-enabled.");
      } catch (e) {
        get().toast("bad", `Couldn't re-enable: ${(e as Error).message}`);
      }
    },

    toast: (tone, text, action) => {
      const id = newId("t");
      set({ toasts: [...get().toasts.slice(-3), { id, tone, text, actionLabel: action?.label, onAction: action?.onAction }] });
      setTimeout(() => get().dismissToast(id), tone === "bad" ? 9000 : 4500);
    },

    dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),

    setPrefs: (p) => {
      const prefs = { ...get().prefs, ...p };
      set({ prefs });
      writeJSON(PREFS_KEY, prefs);
      if (p.theme) {
        try {
          localStorage.setItem("pbs.theme", p.theme);
        } catch {
          /* ignore */
        }
        const dark = p.theme === "dark" || (p.theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
        document.documentElement.classList.toggle("dark", dark);
      }
    },

    setGuardTerms: (raw) => {
      set({ guardTerms: raw });
      writeJSON(GUARD_KEY, raw);
    },

    retryFailed: () => {
      setBase({ outbox: get().outbox.map((i) => (i.state === "failed" ? { ...i, state: "pending", attempts: 0 } : i)) });
      persistOutbox();
      void get().flush();
    },

    clearOutbox: () => {
      setBase({ outbox: [] });
      persistOutbox();
    },

    askSkipReason: (cardId, reason) => set({ skipPrompt: { cardId, reason } }),
    closeSkipPrompt: () => set({ skipPrompt: null }),
  };
});
