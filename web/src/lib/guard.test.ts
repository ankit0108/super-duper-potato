import { aiTells, editSummary, findTerms, firstPersonClaims, parseTerms, phraseHits, tellSummary, unsourcedNumbers } from "./guard";
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
