import type { ReactNode } from "react";
import { safeUrl } from "@/lib/compose";

// The little markdown a chat reply uses: paragraphs, lists, headings, **bold**, *italic*, `code` and links.
// Built as React elements (never raw HTML), and only http(s) links are kept.

const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\)|https?:\/\/[^\s)<>]+|(?<![\w*])\*[^*\n]+\*(?![\w*])|(?<!\w)_[^_\n]+_(?!\w))/g;

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let at = 0;
  let n = 0;
  for (const m of text.matchAll(INLINE)) {
    const tok = m[0];
    if ((m.index ?? 0) > at) out.push(text.slice(at, m.index));
    const k = `${key}-${n++}`;
    if (tok.startsWith("**")) out.push(<strong key={k}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={k} className="rounded bg-surface-2 px-1 text-[0.92em]">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("[")) {
      const [, label, url] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok) ?? [];
      const href = safeUrl(url);
      out.push(href ? <a key={k} href={href} target="_blank" rel="noreferrer" className="text-accent underline-offset-2 hover:underline">{label}</a> : label);
    } else if (tok.startsWith("http")) {
      const clean = tok.replace(/[.,;:!?]+$/, "");
      const href = safeUrl(clean);
      out.push(href ? <a key={k} href={href} target="_blank" rel="noreferrer" className="break-all text-accent underline-offset-2 hover:underline">{clean}</a> : clean);
      if (clean.length < tok.length) out.push(tok.slice(clean.length));
    } else out.push(<em key={k}>{tok.slice(1, -1)}</em>);
    at = (m.index ?? 0) + tok.length;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}

type Block = { kind: "p" | "h"; lines: string[] } | { kind: "ul" | "ol"; items: string[] };

function blocks(text: string): Block[] {
  const out: Block[] = [];
  for (const raw of text.replace(/\r/g, "").split("\n")) {
    const line = raw.trimEnd();
    const last = out[out.length - 1];
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const heading = /^#{1,6}\s+(.*)$/.exec(line);
    if (!line.trim()) out.push({ kind: "p", lines: [] });
    else if (bullet) last?.kind === "ul" ? last.items.push(bullet[1]) : out.push({ kind: "ul", items: [bullet[1]] });
    else if (numbered) last?.kind === "ol" ? last.items.push(numbered[1]) : out.push({ kind: "ol", items: [numbered[1]] });
    else if (heading) out.push({ kind: "h", lines: [heading[1]] });
    else if ((last?.kind === "ul" || last?.kind === "ol") && /^\s{2,}\S/.test(raw)) last.items[last.items.length - 1] += ` ${line.trim()}`;
    else if (last?.kind === "p" && last.lines.length) last.lines.push(line);
    else out.push({ kind: "p", lines: [line] });
  }
  return out.filter((b) => ("items" in b ? b.items.length : b.lines.length));
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={className}>
      {blocks(text).map((b, i) => {
        const k = String(i);
        if ("items" in b) {
          const List = b.kind;
          return (
            <List key={k} className={b.kind === "ul" ? "my-2 list-disc space-y-1 pl-5" : "my-2 list-decimal space-y-1 pl-5"}>
              {b.items.map((it, j) => (
                <li key={j}>{inline(it, `${k}-${j}`)}</li>
              ))}
            </List>
          );
        }
        if (b.kind === "h") return <p key={k} className="mt-3 mb-1 font-semibold">{inline(b.lines[0], k)}</p>;
        return (
          <p key={k} className="my-2 first:mt-0 last:mb-0">
            {b.lines.flatMap((l, j) => (j ? [<br key={`br${j}`} />, ...inline(l, `${k}-${j}`)] : inline(l, `${k}-${j}`)))}
          </p>
        );
      })}
    </div>
  );
}
