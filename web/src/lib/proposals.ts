import type { Proposal } from "@/types";
import type { Tone } from "@/components/ui/Badge";

/** What approving a proposal changes by itself (pbs/playbook.py CHANGE_KEYS). */
export const CHANGE_KEYS = ["patch", "rule", "source", "guide_change", "revert_playbook"] as const;

export function proposalChanges(p: Pick<Proposal, "payload">): boolean {
  const payload = (p.payload ?? {}) as Record<string, unknown>;
  return CHANGE_KEYS.some((k) => !!payload[k]);
}

/**
 * The badge on a proposal. "approved" exists only on the desk, between your tap and the run that applies it
 * (the decision starts a run), so it reads "Applying…" for one that changes something.
 */
export function proposalStatus(status: Proposal["status"], changes: boolean): string {
  switch (status ?? "pending") {
    case "pending":
      return "Waiting for you";
    case "approved":
      return changes ? "Applying…" : "Noted";
    case "applied":
      return "Applied";
    case "noted":
      return "Noted";
    case "rejected":
      return "Rejected";
    case "failed":
      return "Couldn't apply";
    case "expired":
      return "Closed";
    default:
      return String(status);
  }
}

export function proposalTone(status: Proposal["status"]): Tone {
  switch (status ?? "pending") {
    case "pending":
      return "warn";
    case "approved":
      return "info";
    case "failed":
      return "bad";
    case "rejected":
    case "expired":
      return "neutral";
    default:
      return "ok";
  }
}
