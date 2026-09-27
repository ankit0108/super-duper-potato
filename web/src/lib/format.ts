import type { Card, CardStatus, DeskState, FormatName, Platform, SkipReason } from "@/types";

export const PLATFORM_LABEL: Record<Platform, string> = { linkedin: "LinkedIn", x: "X" };

export const FORMAT_LABEL: Record<FormatName, string> = {
  li_text: "Text post",
  x_single: "Single post",
  x_thread: "Thread",
  x_quote: "Quote post",
  x_reply: "Reply angle",
};

export const STATUS_LABEL: Record<CardStatus, string> = {
  drafting: "Drafting",
  suggested: "Suggested",
  needs_input: "Needs input",
  editing: "Editing",
  posted: "Posted",
  skipped: "Skipped",
  expired: "Expired",
  blocked: "Blocked",
  failed: "Failed",
};

export const SKIP_REASONS: Array<{ value: SkipReason; label: string; help: string }> = [
  { value: "not_interesting", label: "Not interesting", help: "Stop suggesting topics like this" },
  { value: "off_brand", label: "Off-brand", help: "Doesn't fit this platform" },
  { value: "wrong_timing", label: "Wrong timing", help: "Fine idea, not today (no penalty)" },
  { value: "too_risky", label: "Too risky", help: "Flag similar topics as sensitive" },
  { value: "already_covered", label: "Already covered", help: "You've said this before" },
  { value: "other", label: "Other", help: "Say why in a note" },
];

export const REWRITE_CHIPS = [
  "Shorter",
  "Sharper hook",
  "More specific",
  "Plainer words",
  "Less formal",
  "Add a takeaway",
  "Different angle",
  "Cut the ending question",
];

export const AFFAIRS_LABEL: Record<string, string> = {
  history: "History behind the news",
  tracker: "Development tracker",
  outlook: "Future outlook",
  opinion: "Opinion (from your stance)",
};

export const HOOK_LABEL: Record<string, string> = {
  question: "Question",
  contrarian: "Contrarian",
  number: "Number",
  story: "Story",
  "how-to": "How-to",
  observation: "Observation",
};

export function pillarLabel(desk: DeskState | null | undefined, platform: Platform, key: string): string {
  const strategy = (desk?.settings?.strategy ?? {}) as Record<string, Record<string, { label?: string }>>;
  return strategy[platform]?.[key]?.label ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function draftText(card: Pick<Card, "draft" | "format">): string {
  const d = card.draft;
  if (!d) return "";
  if (card.format === "x_thread") return (d.posts ?? []).join("\n\n");
  return d.text ?? "";
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return "–";
  return `${(n * 100).toFixed(digits)}%`;
}

export function num(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "–";
  return new Intl.NumberFormat("en-AU", { maximumFractionDigits: 1 }).format(n);
}

export function compact(n: number | null | undefined): string {
  if (n == null) return "–";
  return new Intl.NumberFormat("en-AU", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export const METRIC_FIELDS: Record<Platform, Array<{ key: keyof import("@/types").MetricValues; label: string }>> = {
  linkedin: [
    { key: "impressions", label: "Impressions" },
    { key: "reactions", label: "Reactions" },
    { key: "comments", label: "Comments" },
    { key: "reposts", label: "Reposts" },
    { key: "sends", label: "Sends" },
    { key: "followers_gained", label: "Followers gained" },
    { key: "profile_views", label: "Profile views" },
    { key: "link_clicks", label: "Link clicks" },
  ],
  x: [
    { key: "impressions", label: "Views" },
    { key: "reactions", label: "Likes" },
    { key: "comments", label: "Replies" },
    { key: "reposts", label: "Reposts + quotes" },
    { key: "followers_gained", label: "Follows" },
    { key: "profile_views", label: "Profile visits" },
    { key: "link_clicks", label: "Link clicks" },
  ],
};
