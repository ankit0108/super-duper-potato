import { replaceOpening, swapOpening } from "./Editor";

describe("openings", () => {
  it("replaces the first line, or the first sentence of a one-paragraph post", () => {
    expect(replaceOpening("Old first line.\n\nBody.", "New hook.")).toBe("New hook.\n\nBody.");
    expect(replaceOpening("Old sentence. Second sentence.", "New hook.")).toBe("New hook. Second sentence.");
    expect(replaceOpening("", "New hook.")).toBe("New hook.");
  });

  it("an edited opening changes where it sits in the draft", () => {
    expect(swapOpening("Why now?\n\nBody.", "Why now?", "Why now, really?")).toBe("Why now, really?\n\nBody.");
    expect(swapOpening("Intro. Why now? Body.", "Why now?", "Why this week?")).toBe("Intro. Why this week? Body.");
  });

  it("falls back to replacing the opening when he already rewrote it", () => {
    expect(swapOpening("Something he wrote.\n\nBody.", "Why now?", "Why this week?")).toBe("Why this week?\n\nBody.");
  });
});
