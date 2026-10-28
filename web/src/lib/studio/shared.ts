// Android's Share → PBS Desk: the service worker (public/sw.js) keeps what was shared (text, link, pictures) in
// the "pbs-share" cache and opens #/studio?shared=1, where the Studio picks it up once and clears it.

export const SHARE_CACHE = "pbs-share";

export type SharedContent = { title: string; text: string; url: string; files: Blob[] };

export async function takeShared(): Promise<SharedContent | null> {
  if (typeof caches === "undefined") return null;
  try {
    const cache = await caches.open(SHARE_CACHE);
    const meta = await cache.match("shared/meta");
    if (!meta) return null;
    const info = (await meta.json()) as { title?: string; text?: string; url?: string; files?: number };
    const files: Blob[] = [];
    for (let i = 0; i < Math.min(info.files ?? 0, 10); i++) {
      const res = await cache.match(`shared/file-${i}`);
      if (res) files.push(await res.blob());
    }
    for (const req of await cache.keys()) await cache.delete(req);
    return { title: info.title ?? "", text: info.text ?? "", url: info.url ?? "", files };
  } catch {
    return null;
  }
}

/** What was shared, as the context the Studio sends with your message. */
export function sharedContext(s: SharedContent): { title: string; body: string } {
  const url = s.url || /\bhttps?:\/\/\S+/.exec(s.text)?.[0] || "";
  const host = (() => {
    try {
      return url ? new URL(url).hostname.replace(/^www\./, "") : "";
    } catch {
      return "";
    }
  })();
  const from = /linkedin\.com|lnkd\.in/.test(host) ? "LinkedIn" : /(^|\.)x\.com|twitter\.com|t\.co/.test(host) ? "X" : host;
  const title = s.title.trim() || (from ? `Shared from ${from}` : s.files.length ? "Shared pictures" : "Shared post");
  const body = [
    `Shared${from ? ` from ${from}` : ""} (someone else's post or page, not mine):`,
    s.title.trim() && s.title.trim() !== s.text.trim() ? s.title.trim() : "",
    s.text.trim(),
    url && !s.text.includes(url) ? url : "",
    s.files.length ? `${s.files.length} picture(s) attached.` : "",
  ]
    .filter(Boolean)
    .join("\n");
  return { title, body };
}
