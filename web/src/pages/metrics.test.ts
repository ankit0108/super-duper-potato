import { describe, expect, it } from "vitest";
import type { MetricUpload } from "@/types";
import { isExport, reviewAuthor, uploadSummary } from "./Metrics";

describe("analytics uploads", () => {
  it("sends LinkedIn's and X's exports as they are, and shrinks only screenshots", () => {
    expect(isExport({ name: "Content_2026-09-01_2026-09-27_Ankit.xlsx" })).toBe(true);
    expect(isExport({ name: "account_analytics_content.CSV" })).toBe(true);
    expect(isExport({ name: "Screenshot 2026-09-27.png" })).toBe(false);
    expect(isExport({ name: "report.xls" })).toBe(false);
  });

  it("says what each file gave", () => {
    const upload = {
      id: "upl_1",
      status: "processed",
      results: {
        files: [
          { path: "a.xlsx", kind: "file", platform: "linkedin", metrics: 24, matched: 3, history: 20, needs_review: 1, links_saved: 3, days: 90, followers: 3120 },
          { path: "b.jpg", metrics: 2, needs_review: 1 },
          { path: "c.csv", kind: "file", error: "No analytics found in this file" },
        ],
      },
    } as unknown as MetricUpload;
    expect(uploadSummary(upload)).toEqual([
      "LinkedIn export: 24 posts, 3 matched to PBS posts, 20 earlier, 1 to check, links saved to 3 posts, 90 days of totals, 3,120 followers",
      "Screenshot: 2 number sets, 1 to check",
      "No analytics found in this file",
    ]);
  });

  it("names the model that wrote the review, and why when it wasn't Gemini Pro", () => {
    expect(reviewAuthor({ model: "gemini-3-pro-preview", provider: "gemini_pro" })).toEqual({ model: "gemini-3-pro-preview", note: null });
    const fallback = reviewAuthor({ model: "gemini-3-flash", provider: "gemini" });
    expect(fallback.model).toBe("gemini-3-flash");
    expect(fallback.note).toMatch(/Gemini Pro .* wasn't available/);
    const lite = reviewAuthor({
      model: "gemini-3.5-flash-lite",
      provider: "gemini_lite",
      passed_over: [
        { provider: "gemini_pro", why: "quota" },
        { provider: "gemini", why: "busy" },
      ],
      retry: true,
    });
    expect(lite.note).toBe("Passed over: Gemini Pro: no free quota left on your key; Gemini Flash: busy (server overloaded). A stronger model tries again on the next run.");
  });
});

describe("when to post", () => {
  it("reads a window the way people say it", async () => {
    const { postingWindow } = await import("@/lib/format");
    expect(postingWindow("14:00-16:00")).toBe("2–4pm");
    expect(postingWindow("09:30-11:00")).toBe("9:30–11am");
    expect(postingWindow("11:00-13:00")).toBe("11am–1pm");
    expect(postingWindow("")).toBe("");
  });

  it("turns typed reader tags into hashtags", async () => {
    const { readerTags } = await import("./Settings");
    expect(readerTags("#SoftwareEngineering, MachineLearning  #LLM, , x")).toEqual(["#SoftwareEngineering", "#MachineLearning", "#LLM"]);
  });
});
