import { normalizeTag, sameTag, withHashtags, withoutHashtags } from "./hashtags";
import { platformTips } from "./guard";

describe("hashtags", () => {
  it("normalizes like the pipeline: one #CamelCase word, no numbers or very long tags", () => {
    expect(normalizeTag("#AI agents")).toBe("#AIAgents");
    expect(normalizeTag("process automation")).toBe("#ProcessAutomation");
    expect(normalizeTag("##RPA")).toBe("#RPA");
    expect(normalizeTag("#2026")).toBeNull();
    expect(normalizeTag("   ")).toBeNull();
    expect(normalizeTag(`#${"a".repeat(31)}`)).toBeNull();
    expect(sameTag("#ai", "AI")).toBe(true);
  });

  it("adds the chosen tags as LinkedIn's last line, after an X post, or after post 1 of a thread", () => {
    expect(withHashtags("li_text", { text: "Body.\n", posts: [] }, ["#AI", "#RPA"]).text).toBe("Body.\n\n#AI #RPA");
    expect(withHashtags("x_single", { text: "Short take.", posts: [] }, ["#AI"]).text).toBe("Short take. #AI");
    expect(withHashtags("x_thread", { text: "", posts: ["One.", "Two."] }, ["#AI"]).posts).toEqual(["One. #AI", "Two."]);
    const same = { text: "Body.", posts: [] };
    expect(withHashtags("li_text", same, [])).toBe(same);
  });

  it("takes them off again to compare what went out with the draft", () => {
    expect(withoutHashtags("Body.\n\n#AI #RPA", ["#AI", "#RPA"])).toBe("Body.");
    expect(withoutHashtags("Body with #AI inside.", ["#AI"])).toBe("Body with #AI inside.");
  });
});

describe("platform tips", () => {
  const li = { platform: "linkedin", format: "li_text", hashtags: 3, fold: 210 };
  it("LinkedIn: links, a first line past the fold, long paragraphs, too many tags", () => {
    expect(platformTips("A short opening.\n\nMore.", li)).toEqual([]);
    const tips = platformTips(`${"x".repeat(230)}\n\nRead it at https://example.com/a\n\n${"y ".repeat(220)}`, { ...li, hashtags: 7 });
    expect(tips).toHaveLength(4);
    expect(tips[0]).toMatch(/first comment/);
    expect(tips[1]).toMatch(/230 characters/);
  });
  it("X: links belong in a reply (except quote posts), at most two tags", () => {
    const x = { platform: "x", format: "x_single", hashtags: 1, fold: 210 };
    expect(platformTips("See www.example.com/a now", x)[0]).toMatch(/Put it in a reply/);
    expect(platformTips("See https://example.com/a", { ...x, format: "x_quote" })).toEqual([]);
    expect(platformTips("Fine.", { ...x, hashtags: 3 })[0]).toMatch(/1 or 2 at most/);
  });
});
