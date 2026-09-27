// Mirrors pbs/textutil.py. Both sides are tested against tests/vectors/text.json so the desk's live
// counters and edit ratio match what the pipeline records.

const X_URL_LENGTH = 23;
const X_URL_RE =
  /(?:https?:\/\/[^\s]+)|(?:\b(?:[a-z0-9-]+\.)+(?:com|org|net|io|ai|dev|in|co|gov|edu|app|xyz|me|ly|gl|us|uk|au|news|tech|so)\b(?:\/[^\s]*)?)/gi;
const X_LIGHT: Array<[number, number]> = [
  [0, 4351],
  [8192, 8205],
  [8208, 8223],
  [8242, 8247],
];

const isLight = (cp: number) => X_LIGHT.some(([lo, hi]) => cp >= lo && cp <= hi);

function isEmojiBase(cp: number): boolean {
  return (
    cp >= 0x1f000 ||
    (cp >= 0x2600 && cp <= 0x27bf) ||
    (cp >= 0x2300 && cp <= 0x23ff) ||
    (cp >= 0x2b00 && cp <= 0x2bff) ||
    [0x3030, 0x303d, 0x3297, 0x3299, 0x203c, 0x2049, 0x2122, 0x2139].includes(cp)
  );
}

function isEmojiModifier(cp: number): boolean {
  return cp === 0xfe0f || cp === 0xfe0e || cp === 0x20e3 || (cp >= 0x1f3fb && cp <= 0x1f3ff) || (cp >= 0xe0020 && cp <= 0xe007f);
}

function segmentWeight(segment: string): number {
  const cps = Array.from(segment, (ch) => ch.codePointAt(0)!);
  let i = 0;
  let total = 0;
  const n = cps.length;
  while (i < n) {
    const cp = cps[i];
    if (cp >= 0x1f1e6 && cp <= 0x1f1ff) {
      total += 2;
      i += i + 1 < n && cps[i + 1] >= 0x1f1e6 && cps[i + 1] <= 0x1f1ff ? 2 : 1;
      continue;
    }
    if (cp === 0x23 || cp === 0x2a || (cp >= 0x30 && cp <= 0x39)) {
      let j = i + 1;
      if (j < n && cps[j] === 0xfe0f) j += 1;
      if (j < n && cps[j] === 0x20e3) {
        total += 2;
        i = j + 1;
        continue;
      }
    }
    if (isEmojiBase(cp) || (i + 1 < n && cps[i + 1] === 0xfe0f && cp > 0x7f)) {
      let j = i + 1;
      while (j < n) {
        if (isEmojiModifier(cps[j])) j += 1;
        else if (cps[j] === 0x200d && j + 1 < n && isEmojiBase(cps[j + 1])) j += 2;
        else break;
      }
      total += 2;
      i = j;
      continue;
    }
    total += isLight(cp) ? 1 : 2;
    i += 1;
  }
  return total;
}

/** Weighted length as X counts it: most Latin/Devanagari chars 1, CJK and emoji 2, links 23. */
export function xWeightedLength(text: string | null | undefined): number {
  const t = (text ?? "").normalize("NFC");
  let total = 0;
  let pos = 0;
  for (const m of t.matchAll(X_URL_RE)) {
    const start = m.index ?? 0;
    total += segmentWeight(t.slice(pos, start)) + X_URL_LENGTH;
    pos = start + m[0].length;
  }
  return total + segmentWeight(t.slice(pos));
}

const WORD_CH = /[\p{L}\p{M}\p{N}_]/u;
const SPACE_CH = /[\t\n\v\f\r \p{Zs}\p{Zl}\p{Zp}]/u;

/** Words (letters, marks, digits, underscore) and single punctuation/symbol characters. */
export function editTokens(text: string | null | undefined): string[] {
  const out: string[] = [];
  let buf = "";
  for (const ch of (text ?? "").normalize("NFC")) {
    if (WORD_CH.test(ch)) {
      buf += ch;
      continue;
    }
    if (buf) {
      out.push(buf);
      buf = "";
    }
    if (!SPACE_CH.test(ch)) out.push(ch);
  }
  if (buf) out.push(buf);
  return out;
}

/** Minimum insertions + deletions turning a into b (Myers O((N+M)D)). */
export function myersDistance(a: string[], b: string[]): number {
  const n = a.length;
  const m = b.length;
  if (n === 0 || m === 0) return n + m;
  const max = n + m;
  const offset = max;
  const v = new Int32Array(2 * max + 2);
  for (let d = 0; d <= max; d++) {
    for (let k = -d; k <= d; k += 2) {
      let x = k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1]) ? v[offset + k + 1] : v[offset + k - 1] + 1;
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) {
        x++;
        y++;
      }
      v[offset + k] = x;
      if (x >= n && y >= m) return d;
    }
  }
  return max;
}

/** 0 = posted as drafted, 1 = completely rewritten. Same definition as the pipeline. */
export function editRatio(draft: string | null | undefined, final: string | null | undefined): number {
  const a = editTokens(draft);
  const b = editTokens(final);
  if (!a.length && !b.length) return 0;
  return Math.round((myersDistance(a, b) / (a.length + b.length)) * 10000) / 10000;
}

// ---------------------------------------------------------------------------
// Display diff (keeps whitespace so the result can be rendered)
// ---------------------------------------------------------------------------

export type DiffOp = { op: "eq" | "ins" | "del"; text: string };

function displayTokens(text: string): string[] {
  return (text.normalize("NFC").match(/[\p{L}\p{M}\p{N}_]+\s*|[^\p{L}\p{M}\p{N}_\s]\s*|\s+/gu) ?? []) as string[];
}

export function diffWords(before: string, after: string): DiffOp[] {
  const a = displayTokens(before);
  const b = displayTokens(after);
  const ka = a.map((t) => t.trim());
  const kb = b.map((t) => t.trim());
  const n = a.length;
  const m = b.length;
  const max = n + m;
  if (max === 0) return [];
  const offset = max;
  const v = new Int32Array(2 * max + 2);
  const trace: Int32Array[] = [];
  let found = -1;
  outer: for (let d = 0; d <= max; d++) {
    trace.push(v.slice(offset - d - 1, offset + d + 2));
    for (let k = -d; k <= d; k += 2) {
      let x = k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1]) ? v[offset + k + 1] : v[offset + k - 1] + 1;
      let y = x - k;
      while (x < n && y < m && ka[x] === kb[y]) {
        x++;
        y++;
      }
      v[offset + k] = x;
      if (x >= n && y >= m) {
        found = d;
        break outer;
      }
    }
  }
  // Backtrack.
  const ops: DiffOp[] = [];
  let x = n;
  let y = m;
  for (let d = found; d > 0; d--) {
    const vd = trace[d]; // values for k in [-d-1, d+1] of iteration d (state before iteration d)
    const get = (k: number) => vd[k + d + 1];
    const k = x - y;
    const prevK = k === -d || (k !== d && get(k - 1) < get(k + 1)) ? k + 1 : k - 1;
    const prevX = get(prevK);
    const prevY = prevX - prevK;
    while (x > prevX && y > prevY) {
      ops.push({ op: "eq", text: b[y - 1] });
      x--;
      y--;
    }
    if (x === prevX) ops.push({ op: "ins", text: b[y - 1] });
    else ops.push({ op: "del", text: a[x - 1] });
    x = prevX;
    y = prevY;
  }
  while (x > 0 && y > 0) {
    ops.push({ op: "eq", text: b[y - 1] });
    x--;
    y--;
  }
  ops.reverse();
  // Merge runs.
  const merged: DiffOp[] = [];
  for (const o of ops) {
    const last = merged[merged.length - 1];
    if (last && last.op === o.op) last.text += o.text;
    else merged.push({ ...o });
  }
  return merged;
}

// ---------------------------------------------------------------------------
// Sentences, openings, numbers
// ---------------------------------------------------------------------------

// A sentence ends at . ! ? or । followed by space, but not after an initial ("M. Visvesvaraya") or a common
// abbreviation ("Dr.", "e.g."). Mirrors pbs/textutil.py (shared vectors in tests/vectors/text.json).
const SENTENCE_END = /(?<![\s(][A-Z]\.)(?<!\b(?:Dr|Mr|Ms|St|vs|No)\.)(?<!e\.g\.)(?<!i\.e\.)(?<=[.!?।])\s+|\n+/u;

export function splitSentences(text: string | null | undefined): string[] {
  return (text ?? "")
    .split(SENTENCE_END)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** The first line's first sentence: what a reader sees first. */
export function opening(text: string | null | undefined, limit = 220): string {
  const firstLine = (text ?? "").trim().split("\n", 1)[0]?.trim() ?? "";
  const sentences = splitSentences(firstLine);
  return (sentences[0] ?? firstLine).slice(0, limit);
}

const THREAD_MARK = /^\s*(?:\d{1,2}\s*\/\s*\d{0,2}|\d{1,2}[.)])\s+/gm;
const NUMBER_RE = new RegExp(
  [
    String.raw`(?:[$₹€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn|b|million|billion|trillion|crore|lakh|cr)\b)?)`,
    String.raw`(?:\d[\d,]*(?:\.\d+)?\s?%)`,
    String.raw`(?:\d[\d,]*(?:\.\d+)?\s?(?:x|×|million|billion|trillion|crore|lakh|bn)\b)`,
    String.raw`(?:\b\d[\d,]*\.\d+\b)`,
    String.raw`(?:\b\d{1,3}(?:,\d{2})+,\d{3}\b)`,
    String.raw`(?:\b\d{1,3}(?:,\d{3})+\b)`,
    String.raw`(?:\b\d{2,}\b)`,
  ].join("|"),
  "gi",
);

/** Figures, percentages, amounts and years that a source should back up. */
export function numericClaims(text: string | null | undefined): string[] {
  const cleaned = (text ?? "").replace(THREAD_MARK, " ");
  const found: string[] = [];
  for (const m of cleaned.matchAll(NUMBER_RE)) {
    const token = m[0].trim();
    if (!found.includes(token)) found.push(token);
  }
  return found;
}

export function numberCore(token: string): string {
  const m = token.match(/\d[\d,]*(?:\.\d+)?/);
  return m ? m[0].replace(/,/g, "") : token;
}

export function normalizeNumbers(text: string | null | undefined): string {
  return (text ?? "").replace(/(?<=\d),(?=\d)/g, "");
}

export function wordCount(text: string | null | undefined): number {
  return editTokens(text).filter((t) => WORD_CH.test(t[0])).length;
}

export function truncate(text: string | null | undefined, limit: number): string {
  const t = (text ?? "").replace(/\s+/g, " ").trim();
  if (t.length <= limit) return t;
  let cut = t.slice(0, limit - 1);
  const space = cut.lastIndexOf(" ");
  if (space > limit * 0.6) cut = cut.slice(0, space);
  return cut.replace(/[ ,.;:-]+$/, "") + "…";
}
