/** Shrink a screenshot to a JPEG (max 1600px, ~80% quality) before uploading: smaller repo, same numbers. */
export async function compressImage(file: File, maxSide = 1600, quality = 0.82): Promise<Uint8Array> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const w = Math.round(bitmap.width * scale);
    const h = Math.round(bitmap.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("no canvas");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(bitmap, 0, 0, w, h);
    const blob: Blob = await new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("encode failed"))), "image/jpeg", quality));
    return new Uint8Array(await blob.arrayBuffer());
  } catch {
    return new Uint8Array(await file.arrayBuffer());
  }
}
