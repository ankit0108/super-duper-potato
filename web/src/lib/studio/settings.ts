// The Studio's Gemini key and the models found for it, kept on this device only (like the GitHub token).
import { readJSON, remove, writeJSON } from "@/lib/storage";

const KEY = "pbs.studio.key";
const MODELS = "pbs.studio.models";
const DAY = 24 * 3600 * 1000;

export const getStudioKey = (): string => readJSON<string>(KEY, "");

export function setStudioKey(key: string, models: string[]): void {
  writeJSON(KEY, key.trim());
  writeJSON(MODELS, { tail: key.trim().slice(-6), models, at: Date.now() });
}

export function clearStudioKey(): void {
  remove(KEY);
  remove(MODELS);
}

/** The models found for this key, while they're under a day old (null means look again). */
export function cachedModels(key: string, now = Date.now()): string[] | null {
  const saved = readJSON<{ tail: string; models: string[]; at: number } | null>(MODELS, null);
  if (!saved || saved.tail !== key.trim().slice(-6) || !saved.models?.length || now - saved.at > DAY) return null;
  return saved.models;
}

export const keyHint = (key: string) => (key ? `…${key.slice(-4)}` : "");
