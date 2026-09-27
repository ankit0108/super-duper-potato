// Dates in the desk's configured time zone (Melbourne by default), so "today" matches the pipeline.

export const DEFAULT_TZ = "Australia/Melbourne";

function parts(d: Date, tz: string) {
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const out: Record<string, string> = {};
  for (const p of fmt.formatToParts(d)) out[p.type] = p.value;
  return out;
}

export function toDate(iso: string | Date | null | undefined): Date | null {
  if (!iso) return null;
  const d = iso instanceof Date ? iso : new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "2026-09-28" in the given zone. */
export function localDateKey(iso: string | Date | null | undefined, tz = DEFAULT_TZ): string {
  const d = toDate(iso);
  if (!d) return "";
  const p = parts(d, tz);
  return `${p.year}-${p.month}-${p.day}`;
}

export function formatTime(iso: string | Date | null | undefined, tz = DEFAULT_TZ): string {
  const d = toDate(iso);
  if (!d) return "";
  return new Intl.DateTimeFormat("en-AU", { timeZone: tz, hour: "numeric", minute: "2-digit" }).format(d);
}

export function formatDate(iso: string | Date | null | undefined, tz = DEFAULT_TZ, withYear = false): string {
  const d = toDate(iso);
  if (!d) return "";
  return new Intl.DateTimeFormat("en-AU", {
    timeZone: tz,
    weekday: "short",
    day: "numeric",
    month: "short",
    ...(withYear ? { year: "numeric" } : {}),
  }).format(d);
}

export function formatDateTime(iso: string | Date | null | undefined, tz = DEFAULT_TZ): string {
  const d = toDate(iso);
  if (!d) return "";
  return `${formatDate(d, tz)}, ${formatTime(d, tz)}`;
}

/** "3h ago", "in 2h", "just now". */
export function relative(iso: string | Date | null | undefined, now: Date = new Date()): string {
  const d = toDate(iso);
  if (!d) return "";
  const secs = Math.round((d.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(secs);
  const fmt = (n: number, unit: string) => (secs < 0 ? `${n}${unit} ago` : `in ${n}${unit}`);
  if (abs < 45) return "just now";
  if (abs < 3600) return fmt(Math.round(abs / 60), "m");
  if (abs < 86400 * 1.5) return fmt(Math.round(abs / 3600), "h");
  return fmt(Math.round(abs / 86400), "d");
}

export function isoWeek(date: Date): string {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

export function greeting(tz = DEFAULT_TZ, now: Date = new Date()): string {
  const hour = Number(parts(now, tz).hour);
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

/** Local "YYYY-MM-DDTHH:mm" for <input type="datetime-local"> in the given zone. */
export function toLocalInput(iso: string | Date, tz = DEFAULT_TZ): string {
  const p = parts(toDate(iso)!, tz);
  return `${p.year}-${p.month}-${p.day}T${p.hour === "24" ? "00" : p.hour}:${p.minute}`;
}

/** Inverse of toLocalInput: interpret a wall-clock value in the zone and return ISO UTC. */
export function fromLocalInput(value: string, tz = DEFAULT_TZ): string {
  const [date, time] = value.split("T");
  const [y, mo, d] = date.split("-").map(Number);
  const [h, mi] = (time ?? "00:00").split(":").map(Number);
  let guess = Date.UTC(y, mo - 1, d, h, mi);
  for (let i = 0; i < 2; i++) {
    const p = parts(new Date(guess), tz);
    const asUtc = Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour) % 24, Number(p.minute));
    guess += Date.UTC(y, mo - 1, d, h, mi) - asUtc;
  }
  return new Date(guess).toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function minutesLabel(mins: number | null | undefined): string {
  if (mins == null) return "–";
  if (mins < 1) return "<1 min";
  if (mins < 90) return `${Math.round(mins)} min`;
  return `${(mins / 60).toFixed(1)} h`;
}
