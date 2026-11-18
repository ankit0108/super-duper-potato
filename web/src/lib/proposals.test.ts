import { describe, expect, it } from "vitest";
import { proposalChanges, proposalStatus, proposalTone } from "./proposals";

describe("proposals", () => {
  it("knows what approving changes", () => {
    expect(proposalChanges({ payload: { patch: { learning: { explore_rate: 0.2 } } } })).toBe(true);
    expect(proposalChanges({ payload: { rule: { text: "End with one question." } } })).toBe(true);
    expect(proposalChanges({ payload: { revert_playbook: "pb_v012" } })).toBe(true);
    expect(proposalChanges({ payload: {} })).toBe(false);
    expect(proposalChanges({ payload: undefined })).toBe(false);
  });

  it("says a change is being applied between your tap and the run that applies it", () => {
    expect(proposalStatus("approved", true)).toBe("Applying…");
    expect(proposalStatus("approved", false)).toBe("Noted");
    expect(proposalStatus("applied", true)).toBe("Applied");
    expect(proposalStatus("failed", true)).toBe("Couldn't apply");
    expect(proposalStatus("expired", false)).toBe("Closed");
    expect(proposalStatus(undefined, true)).toBe("Waiting for you");
    expect(proposalTone("approved")).toBe("info");
    expect(proposalTone("failed")).toBe("bad");
  });
});

describe("the weekly source review", () => {
  it("counts as a change, and the sources you remove leave the desk at once", async () => {
    const { applyEvents } = await import("./overlay");
    const review = { id: "prp_1", kind: "source_review", title: "Keep or remove 2 sources?", status: "pending" as const, payload: { review: [{ id: "a", name: "A", why: "x" }, { id: "b", name: "B", why: "y" }] } };
    expect(proposalChanges(review)).toBe(true);
    const desk = { proposals: [review], sources: [{ id: "a", name: "A" }, { id: "b", name: "B" }, { id: "c", name: "C" }] } as never;
    const ev = { id: "e1", at: "2026-11-18T08:00:00Z", type: "proposal.decide", proposal_id: "prp_1", decision: "approve", choices: { a: "remove", b: "keep" } } as never;
    const { desk: view } = applyEvents(desk, [ev]);
    expect(view.sources!.map((s) => s.id)).toEqual(["b", "c"]);
    expect(view.proposals![0].status).toBe("approved");
  });
});
