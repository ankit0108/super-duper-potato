import { aiTells, editSummary, findTerms, firstPersonClaims, liveFlags, parseTerms, phraseHits, quoteCheck, tellSummary, unsourcedNumbers } from "./guard";
import { POST_TYPE_LABEL, postTypeLabel } from "./format";
import tellVectors from "../../../tests/vectors/ai_tells.json";

describe("guard terms", () => {
  it("parses one term per line, commas or semicolons, longest first, without duplicates", () => {
    expect(parseTerms("Contoso\n# a comment\nnorthwind traders; contoso, x\n\nFabrikam")).toEqual(["northwind traders", "Fabrikam", "Contoso"]);
  });

  it("matches case-insensitively across spacing, hyphens and plurals, on word boundaries", () => {
    const terms = parseTerms("Northwind Traders\nContoso");
    expect(findTerms("We met northwind-traders today", terms)).toEqual(["Northwind Traders"]);
    expect(findTerms("Contoso's rollout", terms)).toEqual(["Contoso"]);
    expect(findTerms("contosolution is fine", terms)).toEqual([]);
  });
});

describe("phrases", () => {
  it("matches whole phrases, and punctuation phrases anywhere", () => {
    expect(phraseHits("Big news today. Thoughts?", ["thoughts?", "agree?"])).toEqual(["thoughts?"]);
    expect(phraseHits("Let's delve into it", ["delve"])).toEqual(["delve"]);
    expect(phraseHits("delves are fine", ["delve"])).toEqual([]);
  });
});

describe("fabrication signals", () => {
  it("flags figures that no source mentions", () => {
    const evidence = "The best agent completes 41% of 1,200 tasks.";
    expect(unsourcedNumbers("41% of tasks. What about the other 59%?", evidence)).toEqual(["59%"]);
    expect(unsourcedNumbers("1200 tasks in the benchmark", evidence)).toEqual([]);
  });

  it("flags first-person claims in external drafts", () => {
    expect(firstPersonClaims("I built a bot that failed. The industry is changing.")).toHaveLength(1);
    expect(firstPersonClaims("In my experience, exceptions dominate.")).toHaveLength(1);
    expect(firstPersonClaims("Agents need scoped tools. Audit logs matter.")).toEqual([]);
  });
});

describe("aiTells: the same cases as guardrails.ai_tells (tests/vectors/ai_tells.json)", () => {
  for (const c of tellVectors.ai_tells) {
    it(c.name, () => {
      expect([...new Set(aiTells(c.text).map((t) => t.kind))].sort()).toEqual(c.kinds);
    });
  }

  it("says where each one is, in reading order", () => {
    const tells = aiTells("In today's world, agents matter. It's not about speed, it's about trust.\n\nUltimately, trust wins.");
    expect(tells.map((t) => t.kind)).toEqual(["opener", "contrast", "closer"]);
    expect(tells[1].text).toBe("It's not about speed, it's about trust.");
  });

  it("sums them up for a card's flag, each kind once", () => {
    const tells = [{ kind: "contrast" }, { kind: "dashes" }, { kind: "contrast" }, { kind: "something_new" }];
    expect(tellSummary(tells)).toBe("Sounds like AI: contrast framing, em dashes, something_new");
    expect(tellSummary([{ kind: "closer" }, { kind: "reveal" }])).toBe("Sounds like AI: summary closer, labelled reveal");
  });

  it("says in a line what the editor pass did", () => {
    expect(editSummary(null)).toBeNull();
    expect(editSummary({ before: 3, after: 1, kept: true, provider: "groq" })).toBe("Fixed 2 of 3 AI tells (groq)");
    expect(editSummary({ before: 1, after: 1, kept: false, reason: "added a figure the sources don't have" })).toBe(
      "Found 1 AI tell; kept as written: the edit added a figure the sources don't have",
    );
    expect(editSummary({ before: 2, after: 2, kept: false, skipped: "budget" })).toBe("Found 2 AI tells; not edited: the run was short on model calls");
    expect(editSummary({ before: 2, after: 2, kept: false, skipped: "ProviderError" })).toBe("Found 2 AI tells; not edited: the model call failed");
  });
});

describe("quotes and excerpts stay word for word (guardrails.quote_check)", () => {
  const evidence = "Linus Torvalds: \u201cTalk is cheap. Show me the code.\u201d (word for word on Wikiquote's page for Linus Torvalds).";

  it("passes a quote the source has, whatever the punctuation and quote marks", () => {
    expect(quoteCheck("\u201cTalk is cheap. Show me the code.\u201d\n\u2014 Linus Torvalds\n\nShip the demo.", evidence, "quote")).toEqual([]);
    expect(quoteCheck('"talk is cheap - show me the code" says it all.', evidence, "quote")).toEqual([]);
  });

  it("flags a changed or missing quote, and checks only quote and excerpt posts", () => {
    expect(quoteCheck("\u201cTalk is cheap, show us the code.\u201d \u2014 Linus", evidence, "quote")).toEqual(["Talk is cheap, show us the code."]);
    expect(quoteCheck("Talk is cheap, he said.", evidence, "quote")).toEqual(["the quote isn't in quotation marks"]);
    expect(quoteCheck("\u201cTalk is cheap, show us the code.\u201d", evidence, "funny_take")).toEqual([]);
  });

  it("is part of the live checks while editing", () => {
    const base = { evidence, guardTerms: [], avoid: [], bait: [], external: true, postType: "quote" };
    expect(liveFlags({ ...base, text: "\u201cTalk is cheap. Show me the code.\u201d \u2014 Linus Torvalds" }).quoteChanged).toEqual([]);
    expect(liveFlags({ ...base, text: "\u201cTalk is cheap. Show me code.\u201d \u2014 Linus Torvalds" }).quoteChanged).toHaveLength(1);
  });
});

describe("post types", () => {
  it("names each kind of post the humour and ideas lanes make", () => {
    expect(Object.keys(POST_TYPE_LABEL).sort()).toEqual(["excerpt", "funny_take", "observation", "quote", "thought"]);
    expect(postTypeLabel("funny_take")).toBe("Funny take");
    expect(postTypeLabel("something_new")).toBe("Something new");
  });
});
