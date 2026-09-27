import { findTerms, firstPersonClaims, parseTerms, phraseHits, unsourcedNumbers } from "./guard";

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
