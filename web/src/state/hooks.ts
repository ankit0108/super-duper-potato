import { useEffect, useMemo, useRef, useState } from "react";
import type { Card, DeskState } from "@/types";
import { DEFAULT_TZ, localDateKey } from "@/lib/time";
import { readJSON, writeJSON } from "@/lib/storage";
import { useDesk } from "./store";

export function useView(): DeskState | null {
  return useDesk((s) => s.view);
}

export function useTz(): string {
  return useDesk((s) => s.view?.meta?.timezone ?? DEFAULT_TZ);
}

export function useCard(id: string | undefined): Card | undefined {
  return useDesk((s) => (id ? s.view?.cards?.find((c) => c.id === id) : undefined));
}

/** Re-render on an interval (relative times, staleness). */
export function useNow(ms = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

export function useToday(): string {
  const tz = useTz();
  const now = useNow(60_000);
  return localDateKey(now, tz);
}

/** Active editing time for a card: counts while the tab is visible and there was input in the last minute. */
export function useEditingTimer(cardId: string | undefined, active: boolean): [number, (n: number) => void] {
  const key = `pbs.timer.${cardId}`;
  const [seconds, setSeconds] = useState<number>(() => (cardId ? readJSON<number>(key, 0) : 0));
  const lastInput = useRef(Date.now());
  useEffect(() => {
    if (!cardId || !active) return;
    const mark = () => (lastInput.current = Date.now());
    window.addEventListener("keydown", mark);
    window.addEventListener("pointerdown", mark);
    const t = setInterval(() => {
      if (document.visibilityState !== "visible" || Date.now() - lastInput.current > 60_000) return;
      setSeconds((s) => {
        const n = s + 5;
        writeJSON(key, n);
        return n;
      });
    }, 5000);
    return () => {
      clearInterval(t);
      window.removeEventListener("keydown", mark);
      window.removeEventListener("pointerdown", mark);
    };
  }, [cardId, active, key]);
  const set = (n: number) => {
    setSeconds(n);
    writeJSON(key, n);
  };
  return [seconds, set];
}

export function useMediaQuery(q: string): boolean {
  const [match, setMatch] = useState(() => (typeof window !== "undefined" ? window.matchMedia(q).matches : false));
  useEffect(() => {
    const m = window.matchMedia(q);
    const on = () => setMatch(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [q]);
  return match;
}

export function usePillarLabels(): (platform: string, key: string) => string {
  const view = useView();
  return useMemo(() => {
    const strategy = (view?.settings?.strategy ?? {}) as Record<string, Record<string, { label?: string }>>;
    return (platform: string, key: string) => strategy[platform]?.[key]?.label ?? key;
  }, [view?.settings?.strategy]);
}
