import { beforeEach, describe, expect, it, vi } from "vitest";
import { studioReply } from "./router";
import { setBackupKey } from "./settings";
import type { FallbackOptions } from "./gemini";

const options = (): FallbackOptions => ({ key: "", models: [], system: "Write a draft", search: true,
  contents: [{ role: "user", parts: [{ text: "My supplied source" }] }], onText: vi.fn() });

beforeEach(() => localStorage.clear());

describe("Studio provider fallback", () => {
  it("hands a rate-limited provider to the next and marks the reply as unsearched", async () => {
    setBackupKey("groq", "groq-test"); setBackupKey("openrouter", "router-test");
    const fetcher = vi.fn().mockResolvedValueOnce(new Response("", { status: 429 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ choices: [{ message: { content: "A grounded draft" }, finish_reason: "stop" }] })));
    const result = await studioReply({ ...options(), fetcher });
    expect(result.noSearch).toBe(true);
    expect(result.sources).toEqual([]);
    expect(result.model).toBe("openrouter/openrouter/free");
    const body = JSON.parse(fetcher.mock.calls[1][1].body);
    expect(body.model).toBe("openrouter/free");
    expect(body.messages[0].content).toContain("NO web search");
    expect(body.messages[1].content).toBe("My supplied source");
  });

  it("does not silently drop images into a text-only fallback", async () => {
    setBackupKey("groq", "test");
    const fetcher = vi.fn();
    await expect(studioReply({ ...options(), fetcher, contents: [{ role: "user", parts: [{ inlineData: { mimeType: "image/png", data: "aaa" } }] }] })).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("cancelling prevents the next provider from receiving the chat", async () => {
    setBackupKey("groq", "test");
    const ctrl = new AbortController(); ctrl.abort();
    const fetcher = vi.fn();
    await expect(studioReply({ ...options(), fetcher, signal: ctrl.signal })).rejects.toMatchObject({ name: "AbortError" });
    expect(fetcher).not.toHaveBeenCalled();
  });
});
