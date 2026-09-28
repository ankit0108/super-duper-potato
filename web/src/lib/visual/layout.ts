// Visuals for posts, laid out as pages of shapes and wrapped text: svg.ts draws them, export.ts turns them into
// PNG images or a PDF carousel. Pure geometry (text is measured by a function passed in), so it's testable.
// There's no image model: every word comes from the card's visual, which the pipeline checked like a draft.
import type { Visual } from "@/types";

export type Measure = (text: string, size: number, weight: number) => number;
export type Prim =
  | { t: "rect"; x: number; y: number; w: number; h: number; r?: number; fill: string; stroke?: string; sw?: number }
  | { t: "circle"; cx: number; cy: number; r: number; fill: string; stroke?: string; sw?: number }
  | { t: "text"; x: number; y: number; lines: string[]; size: number; weight: number; fill: string; lh: number; anchor?: "start" | "middle" | "end"; italic?: boolean }
  | { t: "path"; d: string; stroke?: string; sw?: number; fill?: string };
export type Page = { w: number; h: number; bg: string; prims: Prim[] };
export type VisualPlatform = "linkedin" | "x";
export type LayoutOptions = { platform: VisualPlatform; name: string; accent?: string | null; measure?: Measure };

/** LinkedIn: portrait 4:5 (feed images and document carousels). X: landscape 16:9. */
export const SIZES: Record<VisualPlatform, { w: number; h: number }> = { linkedin: { w: 1080, h: 1350 }, x: { w: 1600, h: 900 } };
export const FONT = "Inter, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";
export const DEFAULT_ACCENT = "#4F46E5";

/** Rough glyph widths of a sans-serif, for when there's no canvas to measure with (tests, old browsers). */
export function estimate(text: string, size: number, weight: number): number {
  let units = 0;
  for (const ch of text) units += /[MWmw@%]/.test(ch) ? 0.86 : /[A-Z0-9#&?]/.test(ch) ? 0.64 : /[iljtf.,:;'!|()\s]/.test(ch) ? 0.3 : 0.54;
  return units * size * (weight >= 600 ? 1.06 : 1);
}

let ctx2d: CanvasRenderingContext2D | null | undefined;
export const measureText: Measure = (text, size, weight) => {
  if (ctx2d === undefined) {
    try {
      const jsdom = typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent);
      ctx2d = typeof document !== "undefined" && !jsdom ? document.createElement("canvas").getContext("2d") : null;
    } catch {
      ctx2d = null;
    }
  }
  if (!ctx2d) return estimate(text, size, weight);
  ctx2d.font = `${weight} ${size}px ${FONT}`;
  return ctx2d.measureText(text).width;
};

/** Greedy word wrap; words longer than the line are broken; past maxLines the last line ends in "…". */
export function wrap(text: string, maxWidth: number, size: number, weight: number, maxLines: number, measure: Measure): string[] {
  const out: string[] = [];
  for (const para of (text ?? "").split("\n")) {
    let line = "";
    for (const word of para.split(/\s+/).filter(Boolean)) {
      const next = line ? `${line} ${word}` : word;
      if (measure(next, size, weight) <= maxWidth) {
        line = next;
        continue;
      }
      if (line) out.push(line);
      let rest = word;
      while (rest.length > 1 && measure(rest, size, weight) > maxWidth) {
        let cut = rest.length - 1;
        while (cut > 1 && measure(rest.slice(0, cut), size, weight) > maxWidth) cut--;
        out.push(rest.slice(0, cut));
        rest = rest.slice(cut);
      }
      line = rest;
    }
    if (line) out.push(line);
  }
  if (out.length <= maxLines) return out;
  const kept = out.slice(0, Math.max(1, maxLines));
  let last = kept[kept.length - 1];
  while (last.length > 1 && measure(`${last}…`, size, weight) > maxWidth) last = last.includes(" ") ? last.replace(/\s*\S+$/, "") : last.slice(0, -1);
  kept[kept.length - 1] = `${last.replace(/[\s,.;:–—-]+$/, "")}…`;
  return kept;
}

/** The largest size between `sizes` at which the text fits in maxLines (at the smallest, it's cut with "…"). */
export function fit(text: string, maxWidth: number, sizes: [number, number], weight: number, maxLines: number, measure: Measure): { size: number; lines: string[] } {
  for (let size = sizes[0]; size >= sizes[1]; size -= 2) {
    const lines = wrap(text, maxWidth, size, weight, Number.MAX_SAFE_INTEGER, measure);
    if (lines.length <= maxLines) return { size, lines };
  }
  return { size: sizes[1], lines: wrap(text, maxWidth, sizes[1], weight, maxLines, measure) };
}

// --- colours ---------------------------------------------------------------------------------------------------

export type Palette = { accent: string; accentSoft: string; cover: string; ink: string; muted: string; paper: string; line: string; onDark: string; onDarkMuted: string };

function mix(a: string, b: string, t: number): string {
  const ca = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const cb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return `#${ca.map((v, i) => Math.round(v + (cb[i] - v) * t).toString(16).padStart(2, "0")).join("")}`;
}

export function palette(accent?: string | null): Palette {
  const a = accent && /^#[0-9a-f]{6}$/i.test(accent) ? accent : DEFAULT_ACCENT;
  return {
    accent: a,
    accentSoft: mix(a, "#ffffff", 0.9),
    cover: mix(a, "#0b1020", 0.55),
    ink: "#111827",
    muted: "#4b5563",
    paper: "#ffffff",
    line: mix(a, "#ffffff", 0.72),
    onDark: "#ffffff",
    onDarkMuted: mix(a, "#ffffff", 0.78),
  };
}

// --- building blocks ---------------------------------------------------------------------------------------------

type Geo = { w: number; h: number; m: number; top: number; bottom: number; footer: number; wide: boolean; cw: number };

function geo(platform: VisualPlatform): Geo {
  const { w, h } = SIZES[platform];
  const wide = platform === "x";
  const m = wide ? 80 : 84;
  return { w, h, m, top: wide ? 116 : 140, bottom: h - (wide ? 104 : 136), footer: h - (wide ? 46 : 62), wide, cw: w - 2 * m };
}

const text = (x: number, y: number, lines: string[], size: number, weight: number, fill: string, extra: Partial<Extract<Prim, { t: "text" }>> = {}): Prim => ({
  t: "text",
  x,
  y,
  lines,
  size,
  weight,
  fill,
  lh: Math.round(size * (weight >= 700 ? 1.14 : 1.32)),
  ...extra,
});

const blockHeight = (lines: number, size: number, weight: number) => (lines ? Math.round(size * (weight >= 700 ? 1.14 : 1.32)) * (lines - 1) + size : 0);

/** A straight arrow from (x1,y1) to (x2,y2) with a filled head. */
export function arrow(x1: number, y1: number, x2: number, y2: number, color: string, width = 4): Prim[] {
  const len = Math.hypot(x2 - x1, y2 - y1) || 1;
  const [ux, uy] = [(x2 - x1) / len, (y2 - y1) / len];
  const head = 18;
  const [bx, by] = [x2 - ux * head, y2 - uy * head];
  const [px, py] = [-uy * head * 0.55, ux * head * 0.55];
  return [
    { t: "path", d: `M${r(x1)},${r(y1)} L${r(bx)},${r(by)}`, stroke: color, sw: width },
    { t: "path", d: `M${r(x2)},${r(y2)} L${r(bx + px)},${r(by + py)} L${r(bx - px)},${r(by - py)} Z`, fill: color },
  ];
}
const r = (n: number) => Math.round(n * 10) / 10;

function chrome(page: Page, g: Geo, pal: Palette, name: string, dark: boolean, pageNo?: string, m: Measure = estimate) {
  page.prims.push({ t: "rect", x: g.m, y: g.m - 20, w: 72, h: 10, r: 5, fill: dark ? pal.onDark : pal.accent });
  const size = g.wide ? 26 : 30;
  if (name) page.prims.push(text(g.m, g.footer, wrap(name, g.cw * 0.7, size, 700, 1, m), size, 700, dark ? pal.onDark : pal.ink));
  if (pageNo) page.prims.push(text(g.w - g.m, g.footer, [pageNo], size - 2, 600, dark ? pal.onDarkMuted : pal.muted, { anchor: "end" }));
}

/** Title and subtitle at the top of a one-page visual; returns where the content can start. */
function header(page: Page, v: Visual, g: Geo, pal: Palette, m: Measure): number {
  let y = g.top;
  if (v.title) {
    const t = fit(v.title, g.cw, g.wide ? [54, 38] : [62, 42], 800, 2, m);
    page.prims.push(text(g.m, y + t.size, t.lines, t.size, 800, pal.ink));
    y += blockHeight(t.lines.length, t.size, 800) + 22;
  }
  if (v.subtitle) {
    const size = g.wide ? 28 : 32;
    const lines = wrap(v.subtitle, g.cw, size, 400, 2, m);
    page.prims.push(text(g.m, y + size, lines, size, 400, pal.muted));
    y += blockHeight(lines.length, size, 400) + 18;
  }
  return y + (g.wide ? 30 : 44);
}

/** The source line above the footer; returns the new content bottom. */
function caption(page: Page, v: Visual, g: Geo, pal: Palette, m: Measure, dark = false): number {
  if (!v.caption) return g.bottom;
  const size = g.wide ? 20 : 22;
  const lines = wrap(v.caption, g.cw, size, 500, 2, m);
  const y = g.bottom - blockHeight(lines.length, size, 500) + size;
  page.prims.push(text(g.m, y, lines, size, 500, dark ? pal.onDarkMuted : pal.muted));
  return g.bottom - blockHeight(lines.length, size, 500) - 26;
}

const items = (v: Visual) => (v.items ?? []).filter((it) => (it.title ?? "").trim() || (it.body ?? "").trim());

// --- the six kinds ---------------------------------------------------------------------------------------------

function carousel(v: Visual, g: Geo, pal: Palette, name: string, m: Measure): Page[] {
  const slides = items(v);
  const total = slides.length + 1;
  const cover: Page = { w: g.w, h: g.h, bg: pal.cover, prims: [] };
  const t = fit(v.title || "", g.cw, g.wide ? [84, 50] : [96, 56], 800, g.wide ? 4 : 6, m);
  const subSize = g.wide ? 34 : 40;
  const sub = v.subtitle ? wrap(v.subtitle, g.cw, subSize, 400, 3, m) : [];
  const blockH = blockHeight(t.lines.length, t.size, 800) + (sub.length ? 34 + blockHeight(sub.length, subSize, 400) : 0);
  let y = g.top + Math.max(0, (g.bottom - g.top - blockH) / 2);
  cover.prims.push(text(g.m, y + t.size, t.lines, t.size, 800, pal.onDark));
  y += blockHeight(t.lines.length, t.size, 800) + 34;
  if (sub.length) cover.prims.push(text(g.m, y + subSize, sub, subSize, 400, pal.onDarkMuted));
  cover.prims.push(text(g.w - g.m, g.footer - (g.wide ? 44 : 56), ["Swipe →"], g.wide ? 26 : 30, 700, pal.onDark, { anchor: "end" }));
  chrome(cover, g, pal, name, true, `1 / ${total}`, m);
  const pages = [cover];
  slides.forEach((it, i) => {
    const page: Page = { w: g.w, h: g.h, bg: pal.paper, prims: [] };
    const bottom = i === slides.length - 1 ? caption(page, v, g, pal, m) : g.bottom;
    const numSize = g.wide ? 64 : 88;
    const gapNum = g.wide ? 36 : 52;
    const gapTitle = g.wide ? 28 : 40;
    const tt = fit(it.title ?? "", g.cw, g.wide ? [60, 40] : [74, 48], 800, g.wide ? 3 : 4, m);
    const titleH = blockHeight(tt.lines.length, tt.size, 800);
    const room = Math.max(1, bottom - g.top - numSize - gapNum - titleH - (titleH ? gapTitle : 0));
    const sizes: [number, number] = g.wide ? [40, 28] : [48, 32];
    const bb = it.body ? fit(it.body, g.cw, sizes, 400, Math.max(1, Math.floor(room / Math.round(sizes[1] * 1.32))), m) : { size: sizes[1], lines: [] };
    const lines = bb.lines.slice(0, Math.max(1, Math.floor((room - bb.size) / Math.round(bb.size * 1.32)) + 1));
    const blockH = numSize + gapNum + titleH + (lines.length ? (titleH ? gapTitle : 0) + blockHeight(lines.length, bb.size, 400) : 0);
    // A little above the middle reads best.
    let y2 = g.top + Math.max(0, (bottom - g.top - blockH) * 0.42);
    page.prims.push(text(g.m, y2 + numSize, [String(i + 1).padStart(2, "0")], numSize, 800, pal.accent));
    y2 += numSize + gapNum;
    if (tt.lines.length) {
      page.prims.push(text(g.m, y2 + tt.size, tt.lines, tt.size, 800, pal.ink));
      y2 += titleH + gapTitle;
    }
    if (lines.length) page.prims.push(text(g.m, y2 + bb.size, lines, bb.size, 400, pal.muted));
    chrome(page, g, pal, name, false, `${i + 2} / ${total}`, m);
    pages.push(page);
  });
  return pages;
}

function stepBox(page: Page, it: { title?: string; body?: string }, n: number, x: number, y: number, w: number, h: number, pal: Palette, wide: boolean, m: Measure, numberLeft: boolean) {
  page.prims.push({ t: "rect", x, y, w, h, r: 22, fill: pal.accentSoft, stroke: pal.line, sw: 2 });
  const rad = wide ? 24 : 28;
  const pad = 26;
  const [cx, cy] = numberLeft ? [x + pad + rad, y + h / 2] : [x + pad + rad, y + pad + rad];
  page.prims.push({ t: "circle", cx, cy, r: rad, fill: pal.accent });
  page.prims.push(text(cx, cy + rad * 0.36, [String(n)], rad, 800, "#ffffff", { anchor: "middle" }));
  const tx = numberLeft ? cx + rad + 22 : x + pad;
  const tw = x + w - pad - tx;
  const tSize: [number, number] = wide ? [30, 22] : [34, 24];
  const bSize = wide ? 22 : 25;
  const avail = numberLeft ? h - 2 * 18 : h - (2 * rad + pad + 16) - pad;
  const title = fit(it.title ?? "", tw, tSize, 700, numberLeft ? 1 : 2, m);
  const titleH = blockHeight(title.lines.length, title.size, 700);
  const bodyLines = it.body ? wrap(it.body, tw, bSize, 400, Math.max(0, Math.floor((avail - titleH - 10) / Math.round(bSize * 1.32))), m) : [];
  const blockH = titleH + (bodyLines.length ? 10 + blockHeight(bodyLines.length, bSize, 400) : 0);
  let ty = numberLeft ? y + (h - blockH) / 2 : y + pad + 2 * rad + 16;
  if (title.lines.length) {
    page.prims.push(text(tx, ty + title.size, title.lines, title.size, 700, pal.ink));
    ty += titleH + 10;
  }
  if (bodyLines.length) page.prims.push(text(tx, ty + bSize, bodyLines, bSize, 400, pal.muted));
}

function flow(v: Visual, g: Geo, pal: Palette, name: string, m: Measure): Page {
  const page: Page = { w: g.w, h: g.h, bg: pal.paper, prims: [] };
  const top = header(page, v, g, pal, m);
  const bottom = caption(page, v, g, pal, m);
  const steps = items(v);
  const n = steps.length;
  if (!g.wide) {
    const gap = 46;
    const boxH = Math.min(200, (bottom - top - gap * (n - 1)) / n);
    const used = boxH * n + gap * (n - 1);
    let y = top + Math.max(0, (bottom - top - used) / 2);
    steps.forEach((it, i) => {
      stepBox(page, it, i + 1, g.m, y, g.cw, boxH, pal, false, m, true);
      if (i < n - 1) page.prims.push(...arrow(g.m + 26 + 28, y + boxH + 6, g.m + 26 + 28, y + boxH + gap - 6, pal.accent));
      y += boxH + gap;
    });
  } else {
    const perRow = n <= 4 ? n : Math.ceil(n / 2);
    const rows = n <= 4 ? 1 : 2;
    const gapX = 60;
    const gapY = 56;
    const boxW = (g.cw - gapX * (perRow - 1)) / perRow;
    const boxH = Math.min(rows === 1 ? 330 : 240, (bottom - top - gapY * (rows - 1)) / rows);
    const y0 = top + Math.max(0, (bottom - top - boxH * rows - gapY * (rows - 1)) / 2);
    const pos = steps.map((_, i) => {
      const row = Math.floor(i / perRow);
      const col = row === 0 ? i % perRow : perRow - 1 - (i % perRow); // the second row runs back (a snake)
      return { x: g.m + col * (boxW + gapX), y: y0 + row * (boxH + gapY), row };
    });
    steps.forEach((it, i) => {
      const p = pos[i];
      stepBox(page, it, i + 1, p.x, p.y, boxW, boxH, pal, true, m, false);
      const nx = pos[i + 1];
      if (!nx) return;
      if (nx.row === p.row) {
        const forward = nx.x > p.x;
        const ay = p.y + boxH / 2;
        page.prims.push(...(forward ? arrow(p.x + boxW + 8, ay, nx.x - 8, ay, pal.accent) : arrow(p.x - 8, ay, nx.x + boxW + 8, ay, pal.accent)));
      } else {
        page.prims.push(...arrow(p.x + boxW / 2, p.y + boxH + 8, nx.x + boxW / 2, nx.y - 8, pal.accent));
      }
    });
  }
  chrome(page, g, pal, name, false, undefined, m);
  return page;
}

function compare(v: Visual, g: Geo, pal: Palette, name: string, m: Measure): Page {
  const page: Page = { w: g.w, h: g.h, bg: pal.paper, prims: [] };
  const top = header(page, v, g, pal, m);
  const bottom = caption(page, v, g, pal, m);
  const cols = items(v).slice(0, 2);
  const gap = g.wide ? 96 : 56;
  const colW = (g.cw - gap) / 2;
  const headH = g.wide ? 70 : 80;
  cols.forEach((col, i) => {
    const x = g.m + i * (colW + gap);
    const fill = i === 0 ? "#e5e7eb" : pal.accent;
    const ink = i === 0 ? pal.ink : "#ffffff";
    page.prims.push({ t: "rect", x, y: top, w: colW, h: headH, r: headH / 2, fill });
    const hs = fit(col.title ?? "", colW - 48, g.wide ? [32, 22] : [34, 22], 800, 1, m);
    page.prims.push(text(x + colW / 2, top + headH / 2 + hs.size * 0.36, hs.lines, hs.size, 800, ink, { anchor: "middle" }));
    const points = (col.body ?? "").split("\n").map((p) => p.trim()).filter(Boolean).slice(0, 5);
    const y0 = top + headH + (g.wide ? 40 : 52);
    const avail = bottom - y0;
    const maxLines = g.wide ? 2 : 3;
    // The largest size at which every point fits; the space left over goes between them (within reason).
    let size = g.wide ? 30 : 34;
    let wrapped = points.map((p) => wrap(p, colW - 40, size, 500, maxLines, m));
    const total = () => wrapped.reduce((a, l) => a + blockHeight(l.length, size, 500), 0) + 20 * Math.max(0, wrapped.length - 1);
    while (size > (g.wide ? 22 : 24) && total() > avail) {
      size -= 2;
      wrapped = points.map((p) => wrap(p, colW - 40, size, 500, maxLines, m));
    }
    const spare = Math.max(0, avail - total());
    const spacing = 20 + Math.min(g.wide ? 28 : 40, wrapped.length > 1 ? spare / (wrapped.length - 1) : 0);
    let y = y0;
    for (const lines of wrapped) {
      page.prims.push({ t: "circle", cx: x + 10, cy: y + size * 0.62, r: 7, fill: i === 0 ? pal.muted : pal.accent });
      page.prims.push(text(x + 34, y + size, lines, size, 500, pal.ink));
      y += blockHeight(lines.length, size, 500) + spacing;
    }
  });
  if (cols.length === 2) {
    const cx = g.m + colW + gap / 2;
    page.prims.push({ t: "circle", cx, cy: top + headH / 2, r: g.wide ? 30 : 26, fill: "#ffffff", stroke: pal.line, sw: 3 });
    page.prims.push(text(cx, top + headH / 2 + 8, ["vs"], 22, 800, pal.muted, { anchor: "middle" }));
  }
  chrome(page, g, pal, name, false, undefined, m);
  return page;
}

function list(v: Visual, g: Geo, pal: Palette, name: string, m: Measure): Page {
  const page: Page = { w: g.w, h: g.h, bg: pal.paper, prims: [] };
  const top = header(page, v, g, pal, m);
  const bottom = caption(page, v, g, pal, m);
  const rows = items(v);
  const perCol = g.wide && rows.length > 3 ? Math.ceil(rows.length / 2) : rows.length;
  const cols = Math.ceil(rows.length / perCol);
  const gapX = 64;
  const colW = (g.cw - gapX * (cols - 1)) / cols;
  const rowH = Math.min(g.wide ? 200 : 210, (bottom - top) / perCol);
  rows.forEach((it, i) => {
    const col = Math.floor(i / perCol);
    const x = g.m + col * (colW + gapX);
    const y = top + (i % perCol) * rowH;
    const numSize = g.wide ? 48 : 56;
    const numW = numSize * 1.5;
    page.prims.push(text(x, y + numSize, [String(i + 1)], numSize, 800, pal.accent));
    const tw = colW - numW;
    const title = fit(it.title ?? "", tw, g.wide ? [32, 24] : [36, 26], 700, 2, m);
    const bSize = g.wide ? 23 : 27;
    const titleH = blockHeight(title.lines.length, title.size, 700);
    const bodyLines = it.body ? wrap(it.body, tw, bSize, 400, Math.max(0, Math.floor((rowH - titleH - 36) / Math.round(bSize * 1.32))), m) : [];
    page.prims.push(text(x + numW, y + title.size + 6, title.lines, title.size, 700, pal.ink));
    if (bodyLines.length) page.prims.push(text(x + numW, y + titleH + 16 + bSize, bodyLines, bSize, 400, pal.muted));
    if (i % perCol < perCol - 1 && i < rows.length - 1) page.prims.push({ t: "rect", x: x + numW, y: y + rowH - 16, w: tw, h: 2, fill: pal.line });
  });
  chrome(page, g, pal, name, false, undefined, m);
  return page;
}

function stat(v: Visual, g: Geo, pal: Palette, name: string, m: Measure): Page {
  const page: Page = { w: g.w, h: g.h, bg: pal.paper, prims: [] };
  const top = header(page, v, g, pal, m);
  const bottom = caption(page, v, g, pal, m);
  const it = items(v)[0] ?? { title: "", body: "" };
  const fig = fit(it.title ?? "", g.cw, g.wide ? [230, 90] : [300, 110], 800, 1, m);
  const labelSize: [number, number] = g.wide ? [44, 28] : [50, 32];
  const label = fit(it.body ?? "", g.cw * 0.92, labelSize, 700, g.wide ? 2 : 4, m);
  const blockH = fig.size + 40 + blockHeight(label.lines.length, label.size, 700);
  const y = top + Math.max(0, (bottom - top - blockH) / 2);
  page.prims.push(text(g.w / 2, y + fig.size * 0.9, fig.lines, fig.size, 800, pal.accent, { anchor: "middle" }));
  page.prims.push(text(g.w / 2, y + fig.size + 40 + label.size, label.lines, label.size, 700, pal.ink, { anchor: "middle" }));
  chrome(page, g, pal, name, false, undefined, m);
  return page;
}

function quote(v: Visual, g: Geo, pal: Palette, name: string, m: Measure): Page {
  const page: Page = { w: g.w, h: g.h, bg: pal.accentSoft, prims: [] };
  const top = header(page, v, g, pal, m);
  const bottom = caption(page, v, g, pal, m);
  const it = items(v)[0] ?? { title: "", body: "" };
  const markSize = g.wide ? 170 : 220;
  page.prims.push(text(g.m - 8, top + markSize * 0.72, ["“"], markSize, 800, pal.accent));
  const qTop = top + markSize * 0.62;
  const q = fit(it.body ?? "", g.cw, g.wide ? [52, 32] : [60, 36], 600, g.wide ? 5 : 9, m);
  page.prims.push(text(g.m, qTop + q.size, q.lines, q.size, 600, pal.ink, { italic: true }));
  if (it.title) {
    const size = g.wide ? 28 : 32;
    const y = Math.min(bottom - 8, qTop + blockHeight(q.lines.length, q.size, 600) + 44 + size);
    page.prims.push(text(g.m, y, wrap(`— ${it.title}`, g.cw, size, 700, 1, m), size, 700, pal.muted));
  }
  chrome(page, g, pal, name, false, undefined, m);
  return page;
}

export function layoutVisual(v: Visual, o: LayoutOptions): Page[] {
  const m = o.measure ?? measureText;
  const g = geo(o.platform);
  const pal = palette(o.accent);
  switch (v.kind) {
    case "carousel":
      return carousel(v, g, pal, o.name, m);
    case "flow":
      return [flow(v, g, pal, o.name, m)];
    case "compare":
      return [compare(v, g, pal, o.name, m)];
    case "list":
      return [list(v, g, pal, o.name, m)];
    case "stat":
      return [stat(v, g, pal, o.name, m)];
    case "quote":
      return [quote(v, g, pal, o.name, m)];
    default:
      return [];
  }
}
