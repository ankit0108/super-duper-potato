// Live checks while Ankit edits. Mirrors pbs/guardrails.py so the desk flags the same things the pipeline does.
import type { EditInfo } from "@/types";
import { normalizeNumbers, numberCore, numericClaims, splitSentences, truncate } from "./text";

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const NOT_WORD_BEFORE = "(?<![\\p{L}\\p{N}_])";
const NOT_WORD_AFTER = "(?![\\p{L}\\p{N}_])";

export function parseTerms(raw: string): string[] {
  const out: string[] = [];
  for (const part of raw.split(/[\n,;]+/)) {
    const t = part.trim();
    if (!t || t.startsWith("#") || t.length < 2) continue;
    if (!out.some((o) => o.toLowerCase() === t.toLowerCase())) out.push(t);
  }
  return out.sort((a, b) => b.length - a.length);
}

function termRegex(term: string): RegExp {
  const pieces = term
    .trim()
    .split(/[\s\-_.]+/)
    .filter(Boolean)
    .map(esc);
  return new RegExp(`${NOT_WORD_BEFORE}${pieces.join("[\\s\\-_.]*")}(?:['’]s|s|es)?${NOT_WORD_AFTER}`, "iu");
}

/** Blocklist-style matching: case-insensitive, tolerant of spacing/hyphens, word boundaries. */
export function findTerms(text: string, terms: string[]): string[] {
  if (!text) return [];
  return terms.filter((t) => termRegex(t).test(text));
}

export function phraseHits(text: string, phrases: string[]): string[] {
  const low = (text ?? "").toLowerCase();
  const hits: string[] = [];
  for (const phrase of phrases) {
    const p = phrase.toLowerCase().trim();
    if (!p) continue;
    const found = /^\W|\W$/u.test(p) ? low.includes(p) : new RegExp(`${NOT_WORD_BEFORE}${esc(p)}${NOT_WORD_AFTER}`, "u").test(low);
    if (found && !hits.includes(phrase)) hits.push(phrase);
  }
  return hits;
}

export function unsourcedNumbers(text: string, evidence: string): string[] {
  const ev = normalizeNumbers(evidence).toLowerCase();
  const missing: string[] = [];
  for (const token of numericClaims(text)) {
    const core = numberCore(token);
    if (core && !ev.includes(core) && !missing.includes(token)) missing.push(token);
  }
  return missing;
}

const FIRST_PERSON = [
  /\bI(?:'ve| have|'d| had)? (?:built|shipped|deployed|led|ran|run|saw|seen|found|noticed|learned|learnt|tried|tested|measured|worked|used|implemented|designed|migrated|automated|launched|wrote|created|helped|spent|watched|interviewed|audited|reviewed)\b/i,
  /\bwe(?:'ve| have|'d| had)? (?:built|shipped|deployed|saw|seen|found|noticed|learned|tried|tested|measured|rolled out|implemented|migrated|automated|launched|moved|cut|reduced|saved|replaced|hired|lost|won)\b/i,
  /\b(?:my|our) (?:team|client|clients|company|employer|org|organisation|organization|project|bank|firm|customer|customers|stakeholders?|manager|boss|colleagues?|department|platform|pilot|rollout)\b/i,
  /\bin my (?:experience|work|role|job|day job|last role)\b/i,
  /\bat (?:my|our) (?:company|work|job|firm|bank|client|shop)\b/i,
];

export function firstPersonClaims(text: string): string[] {
  const hits: string[] = [];
  for (const s of splitSentences(text)) {
    if (FIRST_PERSON.some((p) => p.test(s))) {
      const t = truncate(s, 160);
      if (!hits.includes(t)) hits.push(t);
    }
  }
  return hits;
}

// ---------------------------------------------------------------------------
// AI tells: what makes a post read as machine-written. Mirrors guardrails.ai_tells; both are tested against
// tests/vectors/ai_tells.json.
// ---------------------------------------------------------------------------

export type AiTell = { kind: string; text: string };

export const AI_TELL_LABELS: Record<string, string> = {
  contrast: "Contrast framing (“it's not X, it's Y”)",
  reveal: "A labelled reveal (“Here's why”, “The result?”)",
  opener: "A stock opener (“In today's…”, “Imagine…”)",
  closer: "A summary closer (“In short”, “The bottom line”)",
  dashes: "Em dashes",
  emoji_bullets: "Emoji bullets",
  staccato: "Staccato negations (“Not X. Not Y.”)",
  questions: "Stacked rhetorical questions",
  filler: "Filler phrases",
  rhythm: "Every sentence about the same length",
};

/** A tell kind's short name: "Contrast framing", "Summary closer", "Em dashes". */
export function tellName(kind: string): string {
  const name = (AI_TELL_LABELS[kind] ?? kind).replace(/\s*\(.*\)$/, "").replace(/^A /, "");
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** "Sounds like AI: contrast framing, em dashes" from a card's or draft's tells (each kind once). */
export function tellSummary(tells: ReadonlyArray<{ kind: string }>): string {
  const kinds = [...new Set(tells.map((t) => t.kind))];
  return `Sounds like AI: ${kinds.map((k) => tellName(k).toLowerCase()).join(", ")}`;
}

const EDIT_REASONS: Record<string, string> = {
  empty: "the edit came back empty",
  "changed the thread's length": "the edit changed the thread's length",
  "no fewer tells": "the edit didn't remove any",
  "added a figure the sources don't have": "the edit added a figure the sources don't have",
  "dropped a figure": "the edit dropped a figure",
  "blocklist term": "the edit used a blocklist term",
  "an avoided phrase": "the edit used a phrase you avoid",
  "claimed an experience": "the edit claimed an experience the draft didn't",
  "too long": "the edit ran too long",
  "rewrote too much": "the edit changed too much",
};
const EDIT_SKIPS: Record<string, string> = {
  off: "the editor pass is off",
  "degraded run": "the run was short on model calls",
  budget: "the run was short on model calls",
  "run limit": "the run's edit limit was reached",
};

/** What the editor pass did to a draft (card.llm.edit), in a line; null when the draft had no AI tells. */
export function editSummary(edit: EditInfo | null | undefined): string | null {
  if (!edit) return null;
  const before = edit.before ?? 0;
  const tells = `${before} AI tell${before === 1 ? "" : "s"}`;
  if (edit.kept) return `Fixed ${before - (edit.after ?? 0)} of ${tells}${edit.provider ? ` (${edit.provider})` : ""}`;
  if (edit.reason) return `Found ${tells}; kept as written: ${EDIT_REASONS[edit.reason] ?? edit.reason}`;
  if (edit.skipped) return `Found ${tells}; not edited: ${EDIT_SKIPS[edit.skipped] ?? "the model call failed"}`;
  return null;
}

const NEG = "(?:'s\\s+not|\\s+is\\s+not|\\s+isn't)";
const TELL_PATTERNS: Array<[string, RegExp]> = [
  ["contrast", new RegExp(`\\b(?:it|this|that)${NEG}\\s+(?:just\\s+|only\\s+|really\\s+|simply\\s+)?(?:about\\s+)?[^.!?\\n]{1,80}?(?:[,;:—–]|\\s-\\s)\\s*(?:it|this|that)(?:'s|\\s+is)\\b`, "gi")],
  ["contrast", new RegExp(`\\b(?:it|this|that)${NEG}\\s+[^.!?\\n]{1,80}[.!]\\s+(?:it|this|that)(?:'s|\\s+is)\\s`, "gi")],
  ["contrast", /\bnot\s+(?:just|only|merely|simply)\s+[^.!?;\n]{1,80}?,?\s+but\s+(?:also\s+)?\w/gi],
  ["reveal", /(?:^|[.!?]\s+|\n)(?:the|my|our|your)\s+(?:real\s+|big\s+|hard\s+)?(?:result|answer|catch|kicker|takeaway|truth|reality|lesson|twist|secret|problem|fix|upshot|verdict|difference|reason)\s*\?/gi],
  ["reveal", /\bhere(?:'s|\s+is)\s+(?:the\s+(?:thing|catch|kicker|twist|deal|truth|problem|secret|reality|part)|why|what|how|where)\b/gi],
  ["reveal", /\blet's\s+(?:dive|unpack|break\s+(?:it|this|that)\s+down|explore|talk\s+about)\b/gi],
  ["reveal", /\b(?:spoiler(?:\s+alert)?|plot\s+twist|the\s+kicker|hot\s+take|pro\s+tip)\s*[:!]/gi],
  ["staccato", /(?:^|[.!?]\s+|\n)not\s+[^.!?\n]{1,40}[.!]\s+not\s+[^.!?\n]{1,40}[.!]/gi],
  [
    "filler",
    /\b(?:it(?:'s|\s+is)\s+(?:worth\s+noting|important\s+to\s+note|no\s+secret)|plays?\s+a\s+(?:crucial|pivotal|vital|key)\s+role|in\s+the\s+realm\s+of|when\s+it\s+comes\s+to|navigat(?:e|es|ing)\s+the\s+(?:complexit\w*|landscape|world|challenges)|a\s+(?:myriad|plethora)\s+of|in\s+essence|needless\s+to\s+say|it\s+goes\s+without\s+saying|at\s+its\s+core|first\s+and\s+foremost|ever-evolving|fast-paced\s+world|the\s+(?:ever-changing\s+)?landscape\s+of)\b/gi,
  ],
];
const OPENER = /^\s*(?:in\s+today's\b|in\s+a\s+world\s+(?:where|of|that)\b|imagine\b|picture\s+this\b|ever\s+wondered\b|have\s+you\s+ever\s+(?:wondered|thought)\b|let's\s+talk\s+about\b|we\s+all\s+know\b|in\s+the\s+(?:ever-?changing|fast-?paced|rapidly\s+evolving)\b)/i;
const CLOSER = /(?:^|\n|[.!?]\s+)(?:in\s+short|in\s+summary|to\s+sum\s+(?:it\s+)?up|the\s+bottom\s+line|bottom\s+line|ultimately|at\s+the\s+end\s+of\s+the\s+day|in\s+conclusion|the\s+takeaway|tl;?dr)\b/i;
const EMOJI_LINE = /^\s*[\u2190-\u21FF\u2600-\u27BF\u2B00-\u2BFF\u{1F300}-\u{1FAFF}]/u;

function sentenceAround(text: string, start: number, end: number): string {
  const left = start <= 0 ? -1 : Math.max(...[".", "!", "?", "\n"].map((c) => text.lastIndexOf(c, start - 1)));
  const ends = [".", "!", "?", "\n"].map((c) => text.indexOf(c, end)).filter((i) => i !== -1);
  const right = ends.length ? Math.min(...ends) + 1 : text.length;
  return truncate(text.slice(left + 1, right).trim() || text.slice(start, end).trim(), 140);
}

/** Patterns that make a post read as written by AI, each with the sentence it's in, in reading order. */
export function aiTells(text: string | null | undefined): AiTell[] {
  const body = (text ?? "").replace(/[\u2018\u2019]/g, "'");
  if (!body.trim()) return [];
  const found: Array<{ pos: number; kind: string; text: string }> = [];
  const add = (pos: number, kind: string, snippet: string) => {
    if (!found.some((f) => f.kind === kind && f.text === snippet)) found.push({ pos, kind, text: snippet });
  };
  for (const [kind, pattern] of TELL_PATTERNS) {
    pattern.lastIndex = 0;
    for (const m of body.matchAll(pattern)) {
      const lead = m[0].length - m[0].replace(/^[.!?\n ]+/, "").length;
      add(m.index!, kind, sentenceAround(body, m.index! + lead, m.index! + m[0].length));
    }
  }
  const first = body.replace(/^\s+/, "");
  if (OPENER.test(first)) add(0, "opener", truncate(splitSentences(first.split("\n")[0])[0] ?? first, 140));
  const lastPara = body.trim().split(/\n\s*\n/).pop() ?? "";
  const close = CLOSER.exec(lastPara);
  if (close) {
    const offset = body.lastIndexOf(lastPara);
    add(offset + close.index, "closer", sentenceAround(body, offset + close.index + 1, offset + close.index + close[0].length));
  }
  const dashes = (body.match(/—/g) ?? []).length + (body.match(/\s–\s/g) ?? []).length;
  if (dashes > 1) add(body.includes("—") ? body.indexOf("—") : 0, "dashes", `${dashes} em dashes`);
  const emojiLines = body.split("\n").filter((ln) => EMOJI_LINE.test(ln)).map((ln) => ln.trim());
  if (emojiLines.length >= 2) add(body.indexOf(emojiLines[0]), "emoji_bullets", truncate(emojiLines[0], 140));
  const sentences = splitSentences(body.replace(/\n/g, " "));
  for (let i = 0; i + 1 < sentences.length; i++) {
    const [a, b] = [sentences[i], sentences[i + 1]];
    if (a.endsWith("?") && b.endsWith("?")) {
      const at = body.indexOf(a.slice(0, 20));
      add(at >= 0 ? at : 0, "questions", truncate(`${a} ${b}`, 140));
      break;
    }
  }
  const words = sentences.map((s) => s.split(/\s+/).filter(Boolean).length).filter((n) => n >= 3);
  if (words.length >= 5) {
    const mean = words.reduce((a, b) => a + b, 0) / words.length;
    const spread = Math.sqrt(words.reduce((a, w) => a + (w - mean) ** 2, 0) / words.length);
    if (mean >= 6 && spread / mean < 0.25) add(body.length, "rhythm", `${words.length} sentences of about ${Math.round(mean)} words each`);
  }
  return found.sort((a, b) => a.pos - b.pos).map(({ kind, text: t }) => ({ kind, text: t }));
}

export type LiveFlags = {
  blocked: string[];
  unsourced: string[];
  avoid: string[];
  bait: string[];
  firstPerson: string[];
  platform: string[];
  aiTells: AiTell[];
};

const LINK = /\bhttps?:\/\/\S+|\bwww\.\S+\.\S+/i;

/** What tends to cost reach on each platform (the same guidance the drafter gets). */
export function platformTips(text: string, o: { platform: string; format: string; hashtags: number; fold: number }): string[] {
  const tips: string[] = [];
  const hasLink = LINK.test(text);
  if (o.platform === "linkedin") {
    if (hasLink) tips.push("There's a link in the post: LinkedIn tends to show those to fewer people. Put it in the first comment.");
    const first = text.trim().split("\n")[0] ?? "";
    if (first.length > o.fold) tips.push(`The first line is ${first.length} characters: only about ${o.fold} show before "see more".`);
    if (text.split(/\n\s*\n/).some((para) => para.length > 400)) tips.push("A long paragraph: break it up, most people read on a phone.");
    if (o.hashtags > 5) tips.push(`${o.hashtags} hashtags: 3 to 5 work best on LinkedIn.`);
  } else {
    if (hasLink && o.format !== "x_quote") tips.push("There's a link in the post: X tends to show those to fewer people. Put it in a reply.");
    if (o.hashtags > 2) tips.push(`${o.hashtags} hashtags: 1 or 2 at most on X.`);
  }
  return tips;
}

export function liveFlags(opts: {
  text: string;
  evidence: string;
  guardTerms: string[];
  avoid: string[];
  bait: string[];
  external: boolean;
  platform?: { platform: string; format: string; hashtags: number; fold: number };
}): LiveFlags {
  return {
    blocked: findTerms(opts.text, opts.guardTerms),
    unsourced: unsourcedNumbers(opts.text, opts.evidence),
    avoid: phraseHits(opts.text, opts.avoid),
    bait: phraseHits(opts.text, opts.bait),
    firstPerson: opts.external ? firstPersonClaims(opts.text) : [],
    platform: opts.platform ? platformTips(opts.text, opts.platform) : [],
    aiTells: aiTells(opts.text),
  };
}
