// The Studio's Gemini key and the models found for it, kept on this device only (like the GitHub token).
import { readJSON, remove, writeJSON } from "@/lib/storage";

const KEY = "pbs.studio.key";
const MODELS = "pbs.studio.models";
const SPENT = "pbs.studio.spent";
const DAY = 24 * 3600 * 1000;
// Bumped when the kind of models looked for changes (v2: Gemma joined), so a saved list is found again.
const LIST_VERSION = 2;

export const getStudioKey = (): string => readJSON<string>(KEY, "");

export function setStudioKey(key: string, models: string[]): void {
  writeJSON(KEY, key.trim());
  writeJSON(MODELS, { tail: key.trim().slice(-6), models, at: Date.now(), v: LIST_VERSION });
  remove(SPENT); // a new key has its own quota
}

export function clearStudioKey(): void {
  remove(KEY);
  remove(MODELS);
  remove(SPENT);
}

/** The models found for this key, while they're under a day old (null means look again). */
export function cachedModels(key: string, now = Date.now()): string[] | null {
  const saved = readJSON<{ tail: string; models: string[]; at: number; v?: number } | null>(MODELS, null);
  if (!saved || saved.v !== LIST_VERSION || saved.tail !== key.trim().slice(-6) || !saved.models?.length || now - saved.at > DAY) return null;
  return saved.models;
}

// Gemini's free quotas reset at midnight US Pacific time.
const pacificDay = (now: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles" }).format(now);

/** When the free quotas next reset (midnight US Pacific time), give or take a daylight-saving hour. */
export function quotaResetsAt(now = new Date()): Date {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", hourCycle: "h23", hour: "2-digit", minute: "2-digit", second: "2-digit" }).formatToParts(now);
  const n = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  const sinceMidnight = ((n("hour") * 60 + n("minute")) * 60 + n("second")) * 1000;
  return new Date(now.getTime() - sinceMidnight + DAY);
}

/** Models found out of today's free quota: skipped until the quotas reset, so a reply doesn't wait on them. */
export function spentModels(now = new Date()): string[] {
  const saved = readJSON<{ day: string; models: string[] } | null>(SPENT, null);
  return saved && saved.day === pacificDay(now) ? saved.models : [];
}

export function markSpent(model: string, now = new Date()): void {
  writeJSON(SPENT, { day: pacificDay(now), models: [...new Set([...spentModels(now), model])] });
}

export const keyHint = (key: string) => (key ? `…${key.slice(-4)}` : "");
