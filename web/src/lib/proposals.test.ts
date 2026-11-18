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
