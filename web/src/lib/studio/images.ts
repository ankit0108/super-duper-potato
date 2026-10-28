// Pictures for the Studio: shrunk to a JPEG (longest side 1536px) on the device before they're kept in the chat,
// sent to Gemini or saved to the board.
import { newId } from "@/lib/storage";
import type { StudioImage } from "./chats";

export const MAX_IMAGES = 6;

export async function prepImage(file: Blob, name = "", maxSide = 1536, quality = 0.85): Promise<StudioImage> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const w = Math.max(1, Math.round(bitmap.width * scale));
  const h = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("This browser can't read pictures");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close?.();
  return { id: newId("img"), mime: "image/jpeg", width: w, height: h, dataUrl: canvas.toDataURL("image/jpeg", quality), name };
}

export function dataUrlBytes(dataUrl: string): Uint8Array {
  const bin = atob(dataUrl.slice(dataUrl.indexOf(",") + 1));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export const imageFile = (img: StudioImage, i: number) => new File([dataUrlBytes(img.dataUrl).buffer as ArrayBuffer], img.name || `picture-${i + 1}.jpg`, { type: img.mime });
