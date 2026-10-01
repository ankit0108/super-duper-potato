// Draws a laid-out visual page (layout.ts) as a standalone SVG document: the preview on the card and the source
// for the PNG and PDF exports.
import { FONT, type Page, type Prim } from "./layout";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const n = (v: number) => String(Math.round(v * 10) / 10);

function prim(p: Prim): string {
  switch (p.t) {
    case "rect":
      return `<rect x="${n(p.x)}" y="${n(p.y)}" width="${n(p.w)}" height="${n(p.h)}"${p.r ? ` rx="${n(p.r)}"` : ""} fill="${p.fill}"${p.opacity != null ? ` fill-opacity="${p.opacity}"` : ""}${p.stroke ? ` stroke="${p.stroke}" stroke-width="${p.sw ?? 1}"` : ""}/>`;
    case "image":
      // Cover the box (cropping the overflow), as a photo would.
      return `<image href="${esc(p.href)}" x="${n(p.x)}" y="${n(p.y)}" width="${n(p.w)}" height="${n(p.h)}" preserveAspectRatio="xMidYMid slice"/>`;
    case "circle":
      return `<circle cx="${n(p.cx)}" cy="${n(p.cy)}" r="${n(p.r)}" fill="${p.fill}"${p.stroke ? ` stroke="${p.stroke}" stroke-width="${p.sw ?? 1}"` : ""}/>`;
    case "path":
      return `<path d="${p.d}" fill="${p.fill ?? "none"}"${p.stroke ? ` stroke="${p.stroke}" stroke-width="${p.sw ?? 1}" stroke-linecap="round"` : ""}/>`;
    case "text": {
      if (!p.lines.length) return "";
      const spans = p.lines.map((line, i) => `<tspan x="${n(p.x)}"${i ? ` dy="${p.lh}"` : ""}>${esc(line)}</tspan>`).join("");
      return `<text x="${n(p.x)}" y="${n(p.y)}" font-size="${p.size}" font-weight="${p.weight}" fill="${p.fill}"${p.anchor && p.anchor !== "start" ? ` text-anchor="${p.anchor}"` : ""}${p.italic ? ' font-style="italic"' : ""}>${spans}</text>`;
    }
  }
}

export function pageToSvg(page: Page): string {
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${page.w}" height="${page.h}" viewBox="0 0 ${page.w} ${page.h}">`,
    `<g font-family="${esc(FONT)}">`,
    `<rect width="${page.w}" height="${page.h}" fill="${page.bg}"/>`,
    ...page.prims.map(prim),
    "</g></svg>",
  ].join("");
}

export const svgDataUrl = (svg: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

/** Every word on the page, in drawing order (tests and screen-reader fallbacks). */
export const pageText = (page: Page) => page.prims.flatMap((p) => (p.t === "text" ? p.lines : [])).join(" ");
