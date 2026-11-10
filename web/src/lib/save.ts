// Saved for later: a card he wants to post another day. It never expires; with a day, it comes back to the top of
// that day's picks.
import type { Card } from "@/types";

/** A local date key (YYYY-MM-DD) some days on. */
export function addDays(dateKey: string, days: number): string {
  const [y, m, d] = dateKey.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/** The next Monday after a date (a Monday gives the one a week on). */
export function nextMonday(dateKey: string): string {
  const [y, m, d] = dateKey.split("-").map(Number);
  const weekday = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0 Sunday … 6 Saturday
  return addDays(dateKey, ((8 - weekday) % 7) || 7);
}

export function saveChoices(today: string): Array<{ label: string; hint: string; day: string | null }> {
  return [
    { label: "Save for later", hint: "Stays on the board until you post it", day: null },
    { label: "Tomorrow", hint: "Back at the top of tomorrow's picks", day: addDays(today, 1) },
    { label: "In 3 days", hint: dayLabel(addDays(today, 3)), day: addDays(today, 3) },
    { label: "Next Monday", hint: dayLabel(nextMonday(today)), day: nextMonday(today) },
  ];
}

export function dayLabel(dateKey: string): string {
  const [y, m, d] = dateKey.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
}

const OPEN = ["suggested", "needs_input", "blocked", "failed", "editing", "drafting"];

export const isSaved = (c: Card): boolean => !!c.saved && OPEN.includes(c.status);

/** Saved for a day that has come: it belongs with today's picks. */
export const isDue = (c: Card, today: string): boolean => isSaved(c) && !!c.saved?.remind_on && c.saved.remind_on <= today;

/** "Saved", "Saved for today" or "Saved for Thu 12 Nov". */
export function savedLabel(c: Card, today: string): string {
  const day = c.saved?.remind_on;
  if (!day) return "Saved";
  return day <= today ? "Saved for today" : `Saved for ${dayLabel(day)}`;
}

/** A saved news post goes stale: after three days it's worth checking before posting. */
export function savedDaysAgo(c: Card, now: Date = new Date()): number {
  const at = c.saved?.at ? new Date(c.saved.at).getTime() : NaN;
  return Number.isFinite(at) ? Math.floor((now.getTime() - at) / 86_400_000) : 0;
}
