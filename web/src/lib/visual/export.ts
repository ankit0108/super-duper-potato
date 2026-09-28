// Turn visual pages into files: PNG images (one per page) and a PDF carousel, drawn by the browser from the SVG.
import type { Page } from "./layout";
import { buildPdf } from "./pdf";
import { pageToSvg, svgDataUrl } from "./svg";

async function toCanvas(page: Page): Promise<HTMLCanvasElement> {
  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("The visual couldn't be drawn in this browser"));
    img.src = svgDataUrl(pageToSvg(page));
  });
  const canvas = document.createElement("canvas");
  canvas.width = page.w;
  canvas.height = page.h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("This browser can't draw images");
  ctx.fillStyle = page.bg;
  ctx.fillRect(0, 0, page.w, page.h);
  ctx.drawImage(img, 0, 0, page.w, page.h);
  return canvas;
}

export async function pngBlob(page: Page): Promise<Blob> {
  const canvas = await toCanvas(page);
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("PNG export failed"))), "image/png"));
}

export async function pdfBlob(pages: Page[]): Promise<Blob> {
  const parts = [];
  for (const page of pages) {
    const url = (await toCanvas(page)).toDataURL("image/jpeg", 0.92);
    const bin = atob(url.slice(url.indexOf(",") + 1));
    const jpeg = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) jpeg[i] = bin.charCodeAt(i);
    parts.push({ jpeg, width: page.w, height: page.h });
  }
  const bytes = buildPdf(parts);
  return new Blob([bytes.buffer as ArrayBuffer], { type: "application/pdf" });
}

export function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Copies a PNG to the clipboard where the browser allows it (returns false otherwise). */
export async function copyImage(blob: Blob): Promise<boolean> {
  try {
    const Item = (window as unknown as { ClipboardItem?: new (items: Record<string, Blob>) => unknown }).ClipboardItem;
    if (!Item || !navigator.clipboard?.write) return false;
    await navigator.clipboard.write([new Item({ "image/png": blob }) as ClipboardItem]);
    return true;
  } catch {
    return false;
  }
}

export const fileSlug = (title: string) =>
  (title || "visual")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "visual";
