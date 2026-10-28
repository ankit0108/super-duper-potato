// The Studio's model: Gemini, called straight from the browser with a key kept on this device (Settings → Studio).
// Replies stream (server-sent events), Google Search and URL reading are on, and pictures go in with the text.
// Models are found the way the pipeline finds them (pbs/llm/gemini.py pick_models): the newest flash first,
// then flash-lite when it's busy or out of quota.

export const API_BASE = "https://generativelanguage.googleapis.com/v1beta";

export type Part = { text: string } | { inlineData: { mimeType: string; data: string } };
export type Content = { role: "user" | "model"; parts: Part[] };
export type Source = { title: string; url: string };
export type StreamResult = { text: string; sources: Source[]; model: string; finishReason: string | null; searched: string[] };

export class StudioError extends Error {
  constructor(
    message: string,
    public kind: "key" | "quota" | "busy" | "blocked" | "network" | "bad_request",
    public status?: number,
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

async function errorFrom(res: Response): Promise<StudioError> {
  let message = "";
  try {
    const body = (await res.json()) as { error?: { message?: string; status?: string } };
    message = body.error?.message ?? "";
  } catch {
    /* not JSON */
  }
  const low = message.toLowerCase();
  if (res.status === 400 && /api key not valid|api_key_invalid/.test(low)) return new StudioError("That Gemini key isn't valid.", "key", 400);
  if (res.status === 401 || res.status === 403) return new StudioError("Gemini refused the key (it may be restricted or revoked).", "key", res.status);
  if (res.status === 429) return new StudioError(/per day|daily|quota/.test(low) ? "Today's free Gemini quota is used up for this model." : "Gemini is rate-limiting this key for a moment.", "quota", 429);
  if (res.status >= 500) return new StudioError("Gemini is overloaded right now.", "busy", res.status);
  return new StudioError(message ? `Gemini said: ${message.slice(0, 200)}` : `Gemini answered ${res.status}.`, "bad_request", res.status);
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
  const found = [...pickModels(listing, "flash", 2), ...pickModels(listing, "flash-lite", 1)];
  return found.length ? found : ["gemini-flash-latest", "gemini-flash-lite-latest"];
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
  const body = {
    systemInstruction: { parts: [{ text: o.system }] },
    contents: o.contents,
    generationConfig,
    ...(o.search ? { tools: [{ googleSearch: {} }, { urlContext: {} }] } : {}),
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

/** Ask the models in turn: a busy or out-of-quota model hands over to the next. A bad key stops at once. */
export async function streamWithFallback(o: Omit<StreamOptions, "model"> & { models: string[]; onModel?: (m: string) => void }): Promise<StreamResult> {
  let last: unknown = null;
  for (const model of o.models) {
    o.onModel?.(model);
    try {
      return await stream({ ...o, model });
    } catch (e) {
      last = e;
      if (!(e instanceof StudioError) || e.kind === "key" || e.kind === "blocked" || e.kind === "network") throw e;
      if (e.kind === "bad_request" && o.search) {
        // Some models don't take the search tools: try this one once more without them.
        try {
          return await stream({ ...o, model, search: false });
        } catch (e2) {
          last = e2;
        }
      }
    }
  }
  throw last ?? new StudioError("No Gemini model is available for this key.", "busy");
}
