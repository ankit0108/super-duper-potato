// A minimal PDF writer for carousels: one JPEG image per page, no dependencies. LinkedIn shows an uploaded PDF as
// a swipeable document, which is how carousels are posted there.

export type PdfPage = { jpeg: Uint8Array; width: number; height: number };

/** A PDF with one full-page image per page. Page size is the image size at `scale` points per pixel. */
export function buildPdf(pages: PdfPage[], scale = 0.5): Uint8Array {
  const enc = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const offsets: number[] = [];
  let pos = 0;
  const put = (part: string | Uint8Array) => {
    const bytes = typeof part === "string" ? enc.encode(part) : part;
    chunks.push(bytes);
    pos += bytes.length;
  };
  const obj = (num: number, body: string | Array<string | Uint8Array>) => {
    offsets[num] = pos;
    put(`${num} 0 obj\n`);
    for (const part of Array.isArray(body) ? body : [body]) put(part);
    put("\nendobj\n");
  };
  put("%PDF-1.4\n");
  put(new Uint8Array([0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a])); // marks the file as binary
  const pageNum = (i: number) => 3 + i * 3;
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  obj(2, `<< /Type /Pages /Kids [${pages.map((_, i) => `${pageNum(i)} 0 R`).join(" ")}] /Count ${pages.length} >>`);
  pages.forEach((p, i) => {
    const [page, image, content] = [pageNum(i), pageNum(i) + 1, pageNum(i) + 2];
    const w = Math.round(p.width * scale * 100) / 100;
    const h = Math.round(p.height * scale * 100) / 100;
    obj(page, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${w} ${h}] /Resources << /XObject << /Im0 ${image} 0 R >> >> /Contents ${content} 0 R >>`);
    obj(image, [
      `<< /Type /XObject /Subtype /Image /Width ${p.width} /Height ${p.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${p.jpeg.length} >>\nstream\n`,
      p.jpeg,
      "\nendstream",
    ]);
    const draw = `q ${w} 0 0 ${h} 0 0 cm /Im0 Do Q`;
    obj(content, `<< /Length ${enc.encode(draw).length} >>\nstream\n${draw}\nendstream`);
  });
  const count = 3 + pages.length * 3;
  const xref = pos;
  put(`xref\n0 ${count}\n0000000000 65535 f \n`);
  for (let i = 1; i < count; i++) put(`${String(offsets[i]).padStart(10, "0")} 00000 n \n`);
  put(`trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  const out = new Uint8Array(pos);
  let at = 0;
  for (const c of chunks) {
    out.set(c, at);
    at += c.length;
  }
  return out;
}
