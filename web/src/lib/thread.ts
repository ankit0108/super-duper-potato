import { splitSentences, xWeightedLength } from "./text";

/** Split long text into posts of at most `limit` weighted characters, at sentence (then word) boundaries. */
export function splitIntoPosts(text: string, limit = 280): string[] {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  const posts: string[] = [];
  let current = "";
  const push = () => {
    if (current.trim()) posts.push(current.trim());
    current = "";
  };
  const add = (piece: string, sep: string) => {
    const candidate = current ? current + sep + piece : piece;
    if (xWeightedLength(candidate) <= limit) {
      current = candidate;
      return;
    }
    push();
    if (xWeightedLength(piece) <= limit) {
      current = piece;
      return;
    }
    // A single sentence longer than the limit: split on words.
    let chunk = "";
    for (const word of piece.split(/\s+/)) {
      const cand = chunk ? `${chunk} ${word}` : word;
      if (xWeightedLength(cand) > limit && chunk) {
        posts.push(chunk);
        chunk = word;
      } else {
        chunk = cand;
      }
    }
    current = chunk;
  };
  for (const para of paragraphs) {
    const sentences = splitSentences(para);
    sentences.forEach((s, i) => add(s, i === 0 && current ? "\n\n" : " "));
  }
  push();
  return posts.length ? posts : [""];
}

export function numberPosts(posts: string[]): string[] {
  const n = posts.length;
  return posts.map((p, i) => (n > 1 ? `${p}\n\n${i + 1}/${n}` : p));
}

export function threadOverLimit(posts: string[], limit: number): number[] {
  return posts.map((p, i) => (xWeightedLength(p) > limit ? i : -1)).filter((i) => i >= 0);
}
