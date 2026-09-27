// The desk mirrors pbs/textutil.py. Both run the same vectors, so they can't drift apart.
import vectors from "../../../tests/vectors/text.json";
import { diffWords, editRatio, editTokens, myersDistance, numericClaims, opening, splitSentences, truncate, xWeightedLength } from "./text";

type Case<T> = { name: string; expected: T } & Record<string, unknown>;

describe("shared vectors", () => {
  it.each(vectors.x_length as Case<number>[])("x length: $name", (c) => {
    expect(xWeightedLength(c.text as string)).toBe(c.expected);
  });
  it.each(vectors.tokens as Case<string[]>[])("tokens: $name", (c) => {
    expect(editTokens(c.text as string)).toEqual(c.expected);
  });
  it.each(vectors.edit_ratio as Case<number>[])("edit ratio: $name", (c) => {
    expect(editRatio(c.draft as string, c.final as string)).toBeCloseTo(c.expected, 4);
  });
  it.each(vectors.sentences as Case<string[]>[])("sentences: $name", (c) => {
    expect(splitSentences(c.text as string)).toEqual(c.expected);
  });
});

describe("myersDistance", () => {
  it("matches the LCS definition", () => {
    // LCS = a c d f g (5) -> D = 7 + 8 - 10 = 5
    expect(myersDistance(["a", "b", "c", "d", "e", "f", "g"], ["a", "x", "c", "d", "y", "f", "g", "z"])).toBe(5);
  });
});

describe("diffWords", () => {
  const pairs: Array<[string, string]> = [
    ["", ""],
    ["same text", "same text"],
    ["", "all new words here"],
    ["everything goes away", ""],
    ["The quick brown fox jumps", "The slow brown fox leaps high"],
    ["41%.\n\nThat's how many tasks finished.", "41% of tasks finished end to end.\n\nThat's the headline."],
    ["बिहार में नई योजना।", "बिहार में नई सड़क योजना।"],
  ];
  it.each(pairs)("rebuilds both sides: %j -> %j", (before, after) => {
    const ops = diffWords(before, after);
    const rebuilt = (keep: "del" | "ins") =>
      ops
        .filter((o) => o.op === "eq" || o.op === keep)
        .map((o) => o.text)
        .join("");
    // Unchanged words are shown with the new text's spacing, so the old side matches up to whitespace.
    expect(rebuilt("del").replace(/\s+/g, "")).toBe(before.replace(/\s+/g, ""));
    expect(rebuilt("ins")).toBe(after);
  });

  it("keeps unchanged words as one run", () => {
    const ops = diffWords("alpha beta gamma", "alpha beta delta");
    expect(ops[0]).toEqual({ op: "eq", text: "alpha beta " });
    expect(ops.map((o) => o.op)).toEqual(["eq", "del", "ins"]);
  });
});

describe("numbers and openings", () => {
  it("finds figures a source must back up", () => {
    const claims = numericClaims("1/ Revenue grew 37% to $2.5 billion in 2024, up 3.5x. About 1,200 jobs. ₹2,000 crore, 1,23,456 people");
    for (const expected of ["37%", "$2.5 billion", "2024", "3.5x", "1,200", "₹2,000 crore", "1,23,456"]) expect(claims).toContain(expected);
    expect(claims).not.toContain("1");
  });

  it("opening is the first sentence of the first line", () => {
    expect(opening("First line here. Second sentence.\nMore")).toBe("First line here.");
    expect(opening("On this day, M. Visvesvaraya was born. He built dams.")).toBe("On this day, M. Visvesvaraya was born.");
  });

  it("truncates with an ellipsis", () => {
    expect(truncate("word ".repeat(50), 30).endsWith("…")).toBe(true);
    expect(truncate("short", 30)).toBe("short");
  });
});
