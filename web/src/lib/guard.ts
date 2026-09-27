// Live checks while Ankit edits. Mirrors pbs/guardrails.py so the desk flags the same things the pipeline does.
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

export type LiveFlags = {
  blocked: string[];
  unsourced: string[];
  avoid: string[];
  bait: string[];
  firstPerson: string[];
};

export function liveFlags(opts: {
  text: string;
  evidence: string;
  guardTerms: string[];
  avoid: string[];
  bait: string[];
  external: boolean;
}): LiveFlags {
  return {
    blocked: findTerms(opts.text, opts.guardTerms),
    unsourced: unsourcedNumbers(opts.text, opts.evidence),
    avoid: phraseHits(opts.text, opts.avoid),
    bait: phraseHits(opts.text, opts.bait),
    firstPerson: opts.external ? firstPersonClaims(opts.text) : [],
  };
}
