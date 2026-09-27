// Links that open the platforms' own composers with the text prefilled. Ankit still presses Post.

/** Only http(s) links are ever rendered: feed content is untrusted. */
export function safeUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : undefined;
  } catch {
    return undefined;
  }
}

export function linkedInComposeUrl(text: string): string {
  return `https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(text)}`;
}

export function xComposeUrl(text: string, url?: string): string {
  const params = new URLSearchParams({ text });
  if (url) params.set("url", url);
  return `https://x.com/intent/post?${params.toString()}`;
}

export function xSearchUrl(terms: string[], accounts: string[] = []): string {
  let q = terms.filter(Boolean).join(" ");
  const from = accounts.filter(Boolean).map((a) => `from:${a.replace(/^@/, "")}`);
  if (from.length) q = `${q} (${from.join(" OR ")})`.trim();
  return `https://x.com/search?q=${encodeURIComponent(q)}&f=live`;
}

export function xProfileUrl(handle: string): string {
  return `https://x.com/${encodeURIComponent(handle.replace(/^@/, ""))}`;
}

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
