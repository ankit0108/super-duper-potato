import { xWeightedLength } from "./text";
import { numberPosts, splitIntoPosts, threadOverLimit } from "./thread";

describe("splitIntoPosts", () => {
  const long = Array.from({ length: 12 }, (_, i) => `Sentence number ${i + 1} says something useful about agents.`).join(" ");

  it("keeps every post within the limit and loses no words", () => {
    const posts = splitIntoPosts(long, 120);
    expect(posts.length).toBeGreaterThan(3);
    for (const p of posts) expect(xWeightedLength(p)).toBeLessThanOrEqual(120);
    expect(posts.join(" ").split(/\s+/)).toEqual(long.split(/\s+/));
  });

  it("splits at sentence boundaries when it can", () => {
    const posts = splitIntoPosts("First short sentence. Second short sentence.", 30);
    expect(posts).toEqual(["First short sentence.", "Second short sentence."]);
  });

  it("splits a single over-long sentence on words", () => {
    const words = "word ".repeat(100).trim();
    const posts = splitIntoPosts(words, 50);
    for (const p of posts) expect(xWeightedLength(p)).toBeLessThanOrEqual(50);
    expect(posts.join(" ")).toBe(words);
  });

  it("returns one empty post for empty text", () => {
    expect(splitIntoPosts("")).toEqual([""]);
  });
});

describe("thread helpers", () => {
  it("numbers posts only when there are several", () => {
    expect(numberPosts(["a", "b"])).toEqual(["a\n\n1/2", "b\n\n2/2"]);
    expect(numberPosts(["only"])).toEqual(["only"]);
  });

  it("reports posts over the limit", () => {
    expect(threadOverLimit(["short", "x".repeat(300)], 280)).toEqual([1]);
  });
});
