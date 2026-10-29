// The Studio's model: Gemini, called straight from the browser with a key kept on this device (Settings → Studio).
// Replies stream (server-sent events), Google Search and URL reading are on, and pictures go in with the text.
// Models are found the way the pipeline finds them (pbs/llm/gemini.py pick_models): the newest flash first,
// then flash-lite, then Gemma (open models with much larger free limits) when the others are busy or out of quota.

export const API_BASE = "https://generativelanguage.googleapis.com/v1beta";

export type Part = { text: string } | { inlineData: { mimeType: string; data: string } };
export type Content = { role: "user" | "model"; parts: Part[] };
export type Source = { title: string; url: string };
/** `noSearch`: answered without Google Search (its own free quota ran out, or the model doesn't take it). */
export type StreamResult = { text: string; sources: Source[]; model: string; finishReason: string | null; searched: string[]; noSearch?: boolean };

/** `quota`: the day's free requests for that model are gone; `rate`: too many a minute, try again shortly. */
export class StudioError extends Error {
  constructor(
    message: string,
    public kind: "key" | "quota" | "rate" | "busy" | "blocked" | "network" | "bad_request",
    public status?: number,
    public retryAfter?: number,
  ) {
    super(message);
  }
}

const NAME = /^gemini-(\d+(?:\.\d+)*)-(flash-lite|flash|pro)(-.*)?$/;
const PLAIN_SUFFIX = /^(-\d{3}|-latest|-preview(-[\d-]+)?)?$/;

type Listed = { name?: string; supportedGenerationMethods?: string[] };

/** Stable models of a family, newest first, then previews (mirrors pick_models in pbs/llm/gemini.py). */
export function pickModels(listing: Listed[], family: "flash" | "flash-lite", limit = 3): string[] {
  const ranked: Array<{ preview: boolean; ver: number[]; suffix: string; name: string }> = [];
  for (const m of listing) {
    const name = String(m.name ?? "").replace(/^models\//, "");
    if (!(m.supportedGenerationMethods ?? []).includes("generateContent")) continue;
    const match = NAME.exec(name);
    if (!match || match[2] !== family || !PLAIN_SUFFIX.test(match[3] ?? "")) continue;
    const ver = [...match[1].split(".").map(Number), 0, 0, 0].slice(0, 3);
    ranked.push({ preview: (match[3] ?? "").includes("preview"), ver, suffix: match[3] ?? "", name });
  }
  ranked.sort((a, b) => Number(a.preview) - Number(b.preview) || b.ver[0] - a.ver[0] || b.ver[1] - a.ver[1] || b.ver[2] - a.ver[2] || a.suffix.length - b.suffix.length);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of ranked) {
    const key = `${r.preview}:${r.ver.join(".")}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(r.name);
  }
  return out.slice(0, limit);
}

type ErrorDetail = { "@type"?: string; violations?: Array<{ quotaId?: string; quotaMetric?: string }>; retryDelay?: string };

async function errorFrom(res: Response): Promise<StudioError> {
  let message = "";
  let details: ErrorDetail[] = [];
  try {
    const body = (await res.json()) as { error?: { message?: string; status?: string; details?: ErrorDetail[] } };
    message = body.error?.message ?? "";
    details = Array.isArray(body.error?.details) ? body.error!.details! : [];
  } catch {
    /* not JSON */
  }
  const low = message.toLowerCase();
  if (res.status === 400 && /api key not valid|api_key_invalid/.test(low)) return new StudioError("That Gemini key isn't valid.", "key", 400);
  if (res.status === 401 || res.status === 403) return new StudioError("Gemini refused the key (it may be restricted or revoked).", "key", res.status);
  if (res.status === 429) {
    // Every 429 says "quota": the details say whether it's the day's allowance or a per-minute limit
    // (the same reading as the pipeline's, pbs/llm/gemini.py _classify).
    let daily = false;
    let retryAfter: number | undefined;
    for (const d of details) {
      const type = String(d?.["@type"] ?? "");
      if (type.endsWith("QuotaFailure")) for (const v of d.violations ?? []) if (/per_?day/i.test(`${v.quotaId ?? ""} ${v.quotaMetric ?? ""}`)) daily = true;
      if (type.endsWith("RetryInfo")) {
        const m = /([\d.]+)s/.exec(String(d.retryDelay ?? ""));
        if (m) retryAfter = Number(m[1]);
      }
    }
    if (!details.length && /per day|daily/.test(low)) daily = true;
    return daily
      ? new StudioError("Today's free quota for this model is used up.", "quota", 429)
      : new StudioError("Gemini is rate-limiting this key for a moment.", "rate", 429, retryAfter);
  }
  if (res.status >= 500) return new StudioError("Gemini is overloaded right now.", "busy", res.status);
  return new StudioError(message ? `Gemini said: ${message.slice(0, 200)}` : `Gemini answered ${res.status}.`, "bad_request", res.status);
}

const GEMMA = /^gemma-(\d+)n?-(\d+)b-it$/;
export const isGemma = (model: string) => model.startsWith("gemma-");

/** The biggest of the newest Gemma models: no search and no system instructions, but a far larger free quota. */
export function pickGemma(listing: Listed[]): string[] {
  const found = listing
    .map((m) => String(m.name ?? "").replace(/^models\//, ""))
    .filter((n, i) => GEMMA.test(n) && (listing[i].supportedGenerationMethods ?? []).includes("generateContent"))
    .map((n) => {
      const [, ver, size] = GEMMA.exec(n)!;
      return { n, ver: Number(ver), size: Number(size) };
    })
    .sort((a, b) => b.ver - a.ver || b.size - a.size);
  return found.slice(0, 1).map((f) => f.n);
}

/** The models this key can use for the Studio, best first: newest flash models, then flash-lite. */
export async function listModels(key: string, fetcher: typeof fetch = fetch): Promise<string[]> {
  let res: Response;
  try {
    res = await fetcher(`${API_BASE}/models?pageSize=1000`, { headers: { "x-goog-api-key": key } });
  } catch {
    throw new StudioError("Couldn't reach Gemini. Check the connection.", "network");
  }
  if (!res.ok) throw await errorFrom(res);
  const data = (await res.json()) as { models?: Listed[] };
  const listing = data.models ?? [];
  const gemini = [...pickModels(listing, "flash", 2), ...pickModels(listing, "flash-lite", 2)];
  return [...(gemini.length ? gemini : ["gemini-flash-latest", "gemini-flash-lite-latest"]), ...pickGemma(listing)];
}

const major = (model: string) => Number(NAME.exec(model)?.[1]?.split(".")[0] ?? 0);

export type StreamOptions = {
  key: string;
  model: string;
  system: string;
  contents: Content[];
  search: boolean;
  signal?: AbortSignal;
  onText: (soFar: string) => void;
  fetcher?: typeof fetch;
};

/** One streamed answer from one model. Thoughts are skipped; search results come back as sources. */
export async function stream(o: StreamOptions): Promise<StreamResult> {
  const generationConfig: Record<string, unknown> = { maxOutputTokens: 8192 };
  if (major(o.model) >= 3) generationConfig.thinkingConfig = { thinkingLevel: "LOW" };
  else generationConfig.temperature = 0.8;
  // Gemma takes no system instructions and no tools: the instructions lead the conversation instead.
  const gemma = isGemma(o.model);
  const contents: Content[] = gemma
    ? [{ role: "user", parts: [{ text: `Your instructions for this conversation:\n\n${o.system}` }] }, { role: "model", parts: [{ text: "Understood." }] }, ...o.contents]
    : o.contents;
  const body = {
    ...(gemma ? {} : { systemInstruction: { parts: [{ text: o.system }] } }),
    contents,
    generationConfig,
    ...(o.search && !gemma ? { tools: [{ googleSearch: {} }, { urlContext: {} }] } : {}),
  };
  let res: Response;
  try {
    res = await (o.fetcher ?? fetch)(`${API_BASE}/models/${o.model}:streamGenerateContent?alt=sse`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": o.key },
      body: JSON.stringify(body),
      signal: o.signal,
    });
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e;
    throw new StudioError("Couldn't reach Gemini. Check the connection.", "network");
  }
  if (!res.ok || !res.body) throw await errorFrom(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let text = "";
  let finishReason: string | null = null;
  const sources: Source[] = [];
  const searched: string[] = [];
  const handle = (json: string) => {
    let chunk: {
      candidates?: Array<{
        content?: { parts?: Array<{ text?: string; thought?: boolean }> };
        finishReason?: string;
        groundingMetadata?: { groundingChunks?: Array<{ web?: { uri?: string; title?: string } }>; webSearchQueries?: string[] };
      }>;
      promptFeedback?: { blockReason?: string };
    };
    try {
      chunk = JSON.parse(json);
    } catch {
      return;
    }
    if (chunk.promptFeedback?.blockReason) throw new StudioError(`Gemini wouldn't answer that (${chunk.promptFeedback.blockReason}).`, "blocked");
    const cand = chunk.candidates?.[0];
    if (!cand) return;
    for (const p of cand.content?.parts ?? []) if (p.text && !p.thought) text += p.text;
    if (cand.finishReason) finishReason = cand.finishReason;
    for (const g of cand.groundingMetadata?.groundingChunks ?? []) {
      const url = g.web?.uri;
      if (url && !sources.some((s) => s.url === url)) sources.push({ title: g.web?.title || new URL(url).hostname, url });
    }
    for (const q of cand.groundingMetadata?.webSearchQueries ?? []) if (!searched.includes(q)) searched.push(q);
    o.onText(text);
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.search(/\r?\n\r?\n/)) >= 0) {
      const event = buffer.slice(0, cut);
      buffer = buffer.slice(cut).replace(/^\r?\n\r?\n/, "");
      const data = event
        .split(/\r?\n/)
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart())
        .join("\n");
      if (data) handle(data);
    }
  }
  if (buffer.trim().startsWith("data:")) handle(buffer.trim().slice(5).trimStart());
  if (!text.trim()) {
    if (finishReason === "SAFETY" || finishReason === "PROHIBITED_CONTENT") throw new StudioError("Gemini wouldn't answer that.", "blocked");
    throw new StudioError("Gemini sent an empty answer. Try again.", "busy");
  }
  return { text, sources, model: o.model, finishReason, searched };
}

const pause = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => (clearTimeout(t), reject(new DOMException("Stopped", "AbortError"))), { once: true });
  });

export type FallbackOptions = Omit<StreamOptions, "model"> & {
  models: string[];
  onModel?: (m: string) => void;
  /** Models known to be out of today's quota (skipped), and a model found to be (remembered for the day). */
  skip?: (m: string) => boolean;
  onExhausted?: (m: string) => void;
  wait?: (ms: number, signal?: AbortSignal) => Promise<void>;
};

/**
 * Ask the models in turn. On a model that's out of quota or rate-limited with Google Search on, ask it again
 * without search first (search has its own, much smaller, free quota). A per-minute limit with a short wait is
 * waited out once; a model out of the day's quota hands over to the next. A bad key or a blocked prompt stops.
 */
export async function streamWithFallback(o: FallbackOptions): Promise<StreamResult> {
  let last: unknown = null;
  const tried: string[] = [];
  for (const model of o.models) {
    if (o.skip?.(model)) continue;
    o.onModel?.(model);
    tried.push(model);
    let search = o.search && !isGemma(model);
    let waited = false;
    for (;;) {
      try {
        const result = await stream({ ...o, model, search });
        return { ...result, noSearch: o.search && !search };
      } catch (e) {
        last = e;
        if (!(e instanceof StudioError) || e.kind === "key" || e.kind === "blocked" || e.kind === "network") throw e;
        if (search && (e.kind === "bad_request" || e.kind === "quota" || e.kind === "rate")) {
          search = false;
          continue;
        }
        if (e.kind === "rate" && !waited && (e.retryAfter ?? 60) <= 20) {
          waited = true;
          await (o.wait ?? pause)(((e.retryAfter ?? 5) + 1) * 1000, o.signal);
          continue;
        }
        if (e.kind === "quota") o.onExhausted?.(model);
        break;
      }
    }
  }
  if (!tried.length || (last instanceof StudioError && (last.kind === "quota" || last.kind === "rate"))) {
    throw new StudioError(
      tried.length
        ? `Every model this key can use is out of free quota right now (tried ${tried.join(", ")}).`
        : "Every model this key can use is out of today's free quota.",
      "quota",
      429,
    );
  }
  throw last ?? new StudioError("No Gemini model is available for this key.", "busy");
}
