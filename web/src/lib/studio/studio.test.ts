import { card, desk, event } from "@/test/fixtures";
import { applyEvents } from "@/lib/overlay";
import { boardSections } from "@/state/selectors";
import { parseReply, postText } from "./blocks";
import type { StudioChat, StudioMessage } from "./chats";
import { demoReply, demoStream } from "./demo";
import { pickGemma, pickModels, stream, streamWithFallback, StudioError } from "./gemini";
import { contentsFor, evidenceOf, quickActions, redact, systemFor } from "./prompt";
import { sharedContext } from "./shared";

const fence = (name: string, data: unknown) => "```" + name + "\n" + JSON.stringify(data) + "\n```";

describe("parseReply", () => {
  it("splits a reply into text and the blocks the desk can use, in order", () => {
    const reply = `Here's a draft.\n\n${fence("post", { platform: "linkedin", text: "Line one.\n\nLine two.", hooks: ["A", "B"], hashtags: ["AI", "#Agents"], sources: [{ title: "S", url: "https://e.com" }, { title: "Bad", url: "javascript:x" }] })}\n\nOne note.`;
    const segs = parseReply(reply);
    expect(segs.map((s) => s.kind)).toEqual(["text", "post", "text"]);
    const post = segs[1].kind === "post" ? segs[1].post : null;
    expect(post).toMatchObject({ platform: "linkedin", format: "li_text", text: "Line one.\n\nLine two.", hashtags: ["#AI", "#Agents"], sources: [{ title: "S", url: "https://e.com" }] });
  });

  it("reads an X thread, tolerates a trailing comma, and guesses unnamed blocks by shape", () => {
    const thread = "```post\n" + '{"platform": "x", "format": "x_thread", "text": "", "posts": ["One.", "Two."],}' + "\n```";
    const ideas = "```json\n" + JSON.stringify([{ title: "Idea", platform: "x", angle: "a", why: "w" }]) + "\n```";
    const visual = "```\n" + JSON.stringify({ kind: "list", title: "Steps", items: [{ title: "a", body: "b" }] }) + "\n```";
    const segs = parseReply(`${thread}\n${ideas}\n${visual}`);
    expect(segs.map((s) => s.kind)).toEqual(["post", "ideas", "visual"]);
    const post = segs[0].kind === "post" ? segs[0].post : null;
    expect(post?.format).toBe("x_thread");
    expect(postText(post!)).toBe("One.\n\nTwo.");
  });

  it("shows a block that's still streaming as pending, and a broken one as broken", () => {
    expect(parseReply('Writing.\n```post\n{"platform": "lin').map((s) => s.kind)).toEqual(["text", "pending"]);
    expect(parseReply("```visual\n{not json}\n```").map((s) => s.kind)).toEqual(["broken"]);
    // An ordinary code block stays text.
    expect(parseReply("```\nnpm install\n```").map((s) => s.kind)).toEqual(["text"]);
  });
});

describe("pickModels", () => {
  const listing = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-2.0-flash-001", "gemini-2.5-flash-lite", "gemini-3-pro", "gemini-2.5-flash-image", "gemini-2.0-flash"].map((n) => ({
    name: `models/${n}`,
    supportedGenerationMethods: ["generateContent"],
  }));
  it("prefers the newest stable model of the family, previews last, and skips other kinds", () => {
    expect(pickModels(listing, "flash")).toEqual(["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3-flash-preview"]);
    expect(pickModels(listing, "flash-lite")).toEqual(["gemini-2.5-flash-lite"]);
  });
});

function sse(chunks: unknown[], status = 200): typeof fetch {
  return (async () => {
    if (status !== 200) return new Response(JSON.stringify({ error: { message: "quota exceeded per day" } }), { status });
    const body = new ReadableStream({
      start(c) {
        const enc = new TextEncoder();
        // Split mid-event, as the network does.
        const raw = chunks.map((x) => `data: ${JSON.stringify(x)}\r\n\r\n`).join("");
        c.enqueue(enc.encode(raw.slice(0, 37)));
        c.enqueue(enc.encode(raw.slice(37)));
        c.close();
      },
    });
    return new Response(body, { status: 200 });
  }) as unknown as typeof fetch;
}

describe("stream", () => {
  it("streams the text, skips thoughts, and collects search sources", async () => {
    const seen: string[] = [];
    const out = await stream({
      key: "k",
      model: "gemini-2.5-flash",
      system: "s",
      contents: [{ role: "user", parts: [{ text: "hi" }] }],
      search: true,
      onText: (t) => seen.push(t),
      fetcher: sse([
        { candidates: [{ content: { parts: [{ text: "Thinking hard", thought: true }] } }] },
        { candidates: [{ content: { parts: [{ text: "Hello " }] } }] },
        {
          candidates: [
            {
              content: { parts: [{ text: "there." }] },
              finishReason: "STOP",
              groundingMetadata: { groundingChunks: [{ web: { uri: "https://a.com/x", title: "a.com" } }, { web: { uri: "https://a.com/x" } }], webSearchQueries: ["hello"] },
            },
          ],
        },
      ]),
    });
    expect(out.text).toBe("Hello there.");
    expect(seen.at(-1)).toBe("Hello there.");
    expect(out.sources).toEqual([{ title: "a.com", url: "https://a.com/x" }]);
    expect(out.searched).toEqual(["hello"]);
  });

  it("says what went wrong in plain words", async () => {
    const run = (fetcher: typeof fetch) => stream({ key: "k", model: "m", system: "s", contents: [], search: false, onText: () => {}, fetcher });
    await expect(run(sse([], 429))).rejects.toMatchObject({ kind: "quota" });
    await expect(run(sse([], 403))).rejects.toMatchObject({ kind: "key" });
    await expect(run(sse([{ promptFeedback: { blockReason: "SAFETY" } }]))).rejects.toMatchObject({ kind: "blocked" });
    await expect(run(sse([{ candidates: [{ finishReason: "STOP" }] }]))).rejects.toMatchObject({ kind: "busy" });
  });

  it("hands over to the next model when one is busy or out of quota, but stops on a bad key", async () => {
    const calls: string[] = [];
    const fetcher = (async (url: string) => {
      calls.push(String(url));
      if (String(url).includes("first")) return new Response("{}", { status: 503 });
      return sse([{ candidates: [{ content: { parts: [{ text: "From the second." }] } }] }])(url);
    }) as unknown as typeof fetch;
    const out = await streamWithFallback({ key: "k", models: ["first", "second"], system: "s", contents: [], search: true, onText: () => {}, fetcher });
    expect(out.model).toBe("second");
    expect(calls).toHaveLength(2);
    await expect(streamWithFallback({ key: "k", models: ["a", "b"], system: "s", contents: [], search: false, onText: () => {}, fetcher: sse([], 401) })).rejects.toBeInstanceOf(StudioError);
  });
});

const msg = (over: Partial<StudioMessage>): StudioMessage => ({ id: `m${Math.random()}`, role: "user", text: "", at: "2026-10-28T00:00:00Z", ...over });
const img = (id: string) => ({ id, mime: "image/jpeg", width: 10, height: 10, dataUrl: `data:image/jpeg;base64,${id}` });

describe("what the Studio sends", () => {
  it("replaces guard terms before anything leaves the device", () => {
    expect(redact("We built it at Contoso Bank, for contoso-bank's team.", ["Contoso Bank"])).toBe("We built it at [redacted], for [redacted]'s team.");
  });

  it("sends the conversation with recent pictures, folds turns from the same side, and skips failed replies", () => {
    const chat: StudioChat = {
      id: "c",
      title: "t",
      created_at: "",
      updated_at: "",
      messages: [
        msg({ text: "Old photo", images: [img("a")] }),
        msg({ role: "assistant", text: "Nice." }),
        msg({ text: "Two", images: [img("b")] }),
        msg({ role: "assistant", text: "", error: "busy" }),
        msg({ text: "Three", images: [img("c")], context: { kind: "card", title: "Card", body: "About Contoso" } }),
        msg({ text: "Four", images: [img("d")] }),
      ],
    };
    const out = contentsFor(chat, ["Contoso"]);
    expect(out.map((c) => c.role)).toEqual(["user", "model", "user"]);
    expect(out[0].parts).toEqual([{ text: "[1 picture(s) shared earlier]" }, { text: "Old photo" }]);
    const last = out[2].parts;
    expect(last.filter((p) => "inlineData" in p)).toHaveLength(3);
    expect(last).toContainEqual({ text: "About [redacted]" });
    expect(evidenceOf(chat)).toContain("About Contoso");
  });

  it("puts the date and the kit's instructions in the system prompt", () => {
    const s = systemFor({ version: "v", system: "KIT RULES" }, "Ankit", "Australia/Melbourne", new Date("2026-10-28T00:00:00Z"));
    expect(s).toMatch(/^KIT RULES\n\nIt is now Wednesday 28 October 2026/);
    expect(systemFor(null, "Ankit", "UTC")).toContain("You are Ankit's writing partner");
  });

  it("offers actions that fit the moment", () => {
    expect(quickActions({ hasPost: false, shared: true, card: false })[0].label).toBe("Why is it working?");
    expect(quickActions({ hasPost: true, platform: "x", shared: false, card: false }).map((a) => a.label)).toContain("LinkedIn version");
    expect(quickActions({ hasPost: false, shared: false, card: true })[0].label).toBe("Make it better");
  });
});

describe("shared posts", () => {
  it("names where a shared post came from and keeps its text and link", () => {
    const out = sharedContext({ title: "", text: "Great thread on agents https://x.com/a/status/1", url: "", files: [] });
    expect(out.title).toBe("Shared from X");
    expect(out.body).toContain("someone else's post");
    expect(out.body).toContain("https://x.com/a/status/1");
    expect(sharedContext({ title: "", text: "", url: "https://www.linkedin.com/posts/abc", files: [new Blob()] }).body).toContain("1 picture(s) attached.");
  });
});

describe("demo replies", () => {
  it("answers each kind of ask with the block it would get", () => {
    const kinds = (ask: string, picture = false) => parseReply(demoReply(ask, picture, false).text).map((s) => s.kind);
    expect(kinds("Make a LinkedIn carousel from this.")).toContain("visual");
    expect(kinds("Give me post ideas")).toContain("ideas");
    expect(kinds("Write an X thread about this.")).toContain("post");
    expect(kinds("Write a LinkedIn post about this picture.", true)).toContain("post");
    expect(demoReply("Research this", false, false).sources.length).toBeGreaterThan(0);
  });

  it("streams and can be stopped", async () => {
    const ctrl = new AbortController();
    const seen: string[] = [];
    const run = demoStream({ ask: "Give me post ideas", picture: false, shared: false, signal: ctrl.signal, delay: 1, onText: (t) => (seen.push(t), seen.length === 2 && ctrl.abort()) });
    await expect(run).rejects.toMatchObject({ name: "AbortError" });
    expect(seen).toHaveLength(2);
  });
});

describe("saving a Studio post to the board", () => {
  const save = event("studio.save", {
    card_id: "crd_studio",
    platform: "linkedin",
    format: "li_text",
    title: "The demo took a week",
    text: "The demo took a week.",
    hooks: ["Other opening", " "],
    hashtags: ["#AI"],
    images: [{ path: "inbox/blobs/crd_studio_1.jpg", width: 800, height: 600 }],
    visual: { kind: "carousel", title: "Shipping", items: [{ title: "One", body: "Two" }], alt_text: "A carousel", photo: 0 },
  });

  it("shows the card at once, with its pictures and visual, until the pipeline makes it", () => {
    const { desk: out, pending } = applyEvents(desk({ cards: [card({ id: "other" })] }), [save]);
    const made = out.cards!.find((c) => c.id === "crd_studio")!;
    expect(made).toMatchObject({ kind: "studio", status: "suggested", draft: { text: "The demo took a week.", posts: [] }, hashtags: ["#AI"] });
    expect(made.hooks).toEqual([{ type: "observation", text: "Other opening" }]);
    expect(made.attachments).toEqual([{ path: "inbox/blobs/crd_studio_1.jpg", content_type: "image/jpeg", width: 800, height: 600 }]);
    expect(made.visual?.image).toMatchObject({ path: "inbox/blobs/crd_studio_1.jpg", provider: "your photo" });
    expect(pending.cards.has("crd_studio")).toBe(true);
    // Sent twice (a retry): still one card.
    expect(applyEvents(out, [save]).desk.cards!.filter((c) => c.id === "crd_studio")).toHaveLength(1);
  });

  it("lists it with today's picks, labelled as yours", () => {
    const studio = card({ id: "s1", kind: "studio", created_at: "2026-09-28T23:00:00Z", status: "suggested" });
    const out = boardSections(desk({ cards: [studio] }), "2026-09-29", "Australia/Melbourne", "all");
    expect(out.today.linkedin.map((c) => c.id)).toEqual(["s1"]);
    expect(out.thisWeek).toHaveLength(0);
  });
});


describe("free quotas", () => {
  const quota429 = (perDay: boolean, retry = "7s") =>
    new Response(
      JSON.stringify({
        error: {
          message: "You exceeded your current quota, please check your plan and billing details.",
          details: [
            { "@type": "type.googleapis.com/google.rpc.QuotaFailure", violations: [{ quotaId: perDay ? "GenerateRequestsPerDayPerProjectPerModel-FreeTier" : "GenerateRequestsPerMinutePerProjectPerModel-FreeTier" }] },
            { "@type": "type.googleapis.com/google.rpc.RetryInfo", retryDelay: retry },
          ],
        },
      }),
      { status: 429 },
    );
  const ok = (text: string) => sse([{ candidates: [{ content: { parts: [{ text }] }, finishReason: "STOP" }] }])("");
  type Call = { model: string; body: { tools?: unknown; systemInstruction?: unknown; contents: Array<{ parts: Array<{ text?: string }> }> } };
  const recorder = (answer: (c: Call, n: number) => Response | Promise<Response>) => {
    const calls: Call[] = [];
    const fetcher = (async (url: string, init: RequestInit) => {
      const call = { model: /models\/([^:]+):/.exec(String(url))![1], body: JSON.parse(String(init.body)) };
      calls.push(call);
      return answer(call, calls.length);
    }) as unknown as typeof fetch;
    return { calls, fetcher };
  };
  const base = { key: "k", system: "RULES", contents: [{ role: "user" as const, parts: [{ text: "hi" }] }], onText: () => {} };

  it("tells a day's quota from a per-minute limit (every 429 says \"quota\")", async () => {
    const run = (res: Response) => stream({ ...base, model: "m", search: false, fetcher: (async () => res) as unknown as typeof fetch });
    await expect(run(quota429(true))).rejects.toMatchObject({ kind: "quota" });
    await expect(run(quota429(false, "12s"))).rejects.toMatchObject({ kind: "rate", retryAfter: 12 });
  });

  it("answers without Google Search when search's own quota is gone, and says so", async () => {
    const { calls, fetcher } = recorder((c) => (c.body.tools ? quota429(true) : ok("Done without search.")));
    const out = await streamWithFallback({ ...base, models: ["gemini-2.5-flash", "gemini-2.5-flash-lite"], search: true, fetcher });
    expect(out).toMatchObject({ text: "Done without search.", model: "gemini-2.5-flash", noSearch: true });
    expect(calls.map((c) => [c.model, !!c.body.tools])).toEqual([["gemini-2.5-flash", true], ["gemini-2.5-flash", false]]);
  });

  it("waits out a short per-minute limit once, and remembers a model whose day is used up", async () => {
    const waits: number[] = [];
    const spent: string[] = [];
    const { calls, fetcher } = recorder((c, n) => (c.model === "a" ? quota429(true) : n === 2 ? quota429(false, "3s") : ok("From b.")));
    const out = await streamWithFallback({ ...base, models: ["a", "b"], search: false, fetcher, onExhausted: (m) => spent.push(m), wait: async (ms) => void waits.push(ms) });
    expect(out.text).toBe("From b.") ;
    expect(spent).toEqual(["a"]);
    expect(waits).toEqual([4000]);
    expect(calls.map((c) => c.model)).toEqual(["a", "b", "b"]);
  });

  it("falls back to Gemma, which takes the instructions in the conversation and no tools", async () => {
    const { calls, fetcher } = recorder((c) => (c.model.startsWith("gemma") ? ok("From Gemma.") : quota429(true)));
    const out = await streamWithFallback({ ...base, models: ["gemini-2.5-flash", "gemma-3-27b-it"], search: true, fetcher });
    expect(out).toMatchObject({ model: "gemma-3-27b-it", text: "From Gemma." });
    const gemma = calls.at(-1)!.body;
    expect(gemma.systemInstruction).toBeUndefined();
    expect(gemma.tools).toBeUndefined();
    expect(gemma.contents[0].parts[0].text).toContain("RULES");
    expect(gemma.contents.at(-1)!.parts[0].text).toBe("hi");
  });

  it("skips models already out of today's quota, and says when they all are", async () => {
    const { calls, fetcher } = recorder(() => ok("From b."));
    await streamWithFallback({ ...base, models: ["a", "b"], search: false, fetcher, skip: (m) => m === "a" });
    expect(calls.map((c) => c.model)).toEqual(["b"]);
    await expect(streamWithFallback({ ...base, models: ["a"], search: false, fetcher, skip: () => true })).rejects.toMatchObject({ kind: "quota" });
    const tired = recorder(() => quota429(true));
    await expect(streamWithFallback({ ...base, models: ["a", "b"], search: false, fetcher: tired.fetcher })).rejects.toThrow("tried a, b");
  });

  it("picks the biggest of the newest Gemma models", () => {
    const listing = ["gemma-3-12b-it", "gemma-3-27b-it", "gemma-2-27b-it", "gemma-3n-e4b-it", "gemma-3-27b-pt"].map((n) => ({ name: `models/${n}`, supportedGenerationMethods: ["generateContent"] }));
    expect(pickGemma(listing)).toEqual(["gemma-3-27b-it"]);
  });
});
