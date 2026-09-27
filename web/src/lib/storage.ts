// Browser storage can be unavailable (private mode, blocked site data). Every access is guarded and the
// desk keeps working from memory.

const memory = new Map<string, string>();

export function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return memory.has(key) ? (JSON.parse(memory.get(key)!) as T) : fallback;
    return JSON.parse(raw) as T;
  } catch {
    try {
      return memory.has(key) ? (JSON.parse(memory.get(key)!) as T) : fallback;
    } catch {
      return fallback;
    }
  }
}

export function writeJSON(key: string, value: unknown): boolean {
  const raw = JSON.stringify(value);
  memory.set(key, raw);
  try {
    localStorage.setItem(key, raw);
    return true;
  } catch {
    return false;
  }
}

export function remove(key: string): void {
  memory.delete(key);
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export function keysWithPrefix(prefix: string): string[] {
  const keys = new Set<string>([...memory.keys()].filter((k) => k.startsWith(prefix)));
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k?.startsWith(prefix)) keys.add(k);
    }
  } catch {
    /* ignore */
  }
  return [...keys];
}

export function newId(prefix: string): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}`;
  const bytes = new Uint8Array(4);
  crypto.getRandomValues(bytes);
  const rand = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${prefix}_${stamp}_${rand}`;
}
