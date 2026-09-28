import type { Visual } from "@/types";
import { card, desk, event } from "@/test/fixtures";
import { applyEvents } from "../overlay";
import { demoVisual, processDemoEvents } from "../demo";
import { SIZES, estimate, fit, layoutVisual, palette, wrap, type Page } from "./layout";
import { buildPdf } from "./pdf";
import { pageText, pageToSvg } from "./svg";

const measure = estimate;
const visual = (over: Partial<Visual>): Visual => ({ kind: "carousel", title: "What the benchmark says", items: [], alt_text: "", ...over }) as Visual;
const texts = (page: Page) => page.prims.filter((p): p is Extract<Page["prims"][number], { t: "text" }> => p.t === "text");

describe("text layout", () => {
  it("wraps within the width and cuts with an ellipsis past the last line", () => {
    const lines = wrap("one two three four five six seven eight nine ten", 200, 30, 400, 10, measure);
    expect(lines.length).toBeGreaterThan(1);
    expect(lines.every((l) => measure(l, 30, 400) <= 200)).toBe(true);
    const cut = wrap("one two three four five six seven eight nine ten", 200, 30, 400, 2, measure);
    expect(cut).toHaveLength(2);
    expect(cut[1].endsWith("…")).toBe(true);
    expect(wrap("Supercalifragilisticexpialidocious", 120, 30, 400, 5, measure).every((l) => measure(l, 30, 400) <= 120)).toBe(true);
  });

  it("fits text at the largest size that keeps it within its lines", () => {
    const short = fit("Short title", 900, [96, 56], 800, 2, measure);
    expect(short.size).toBe(96);
    const long = fit("A much longer title that needs to shrink to fit on two lines at most in this box", 700, [96, 40], 800, 2, measure);
    expect(long.size).toBeLessThan(96);
    expect(long.lines.length).toBeLessThanOrEqual(2);
  });

  it("derives a palette from the accent and falls back on a bad one", () => {
    expect(palette("#123456").accent).toBe("#123456");
    expect(palette("red").accent).toBe("#4F46E5");
  });
});

describe("layoutVisual", () => {
  const slides = [
    { title: "The headline number", body: "The best agent completed 41% of 1,200 tasks." },
    { title: "Where it breaks", body: "Exception handling." },
    { title: "What to do", body: "Test on your exceptions." },
  ];

  it("a carousel is a cover plus one page per slide, numbered, at the platform's size", () => {
    const pages = layoutVisual(visual({ items: slides, subtitle: "For operations teams", caption: "Source: AgentBench" }), { platform: "linkedin", name: "Ankit", measure });
    expect(pages).toHaveLength(4);
    expect(pages.every((p) => p.w === SIZES.linkedin.w && p.h === SIZES.linkedin.h)).toBe(true);
    expect(pageText(pages[0])).toContain("What the benchmark says");
    expect(pageText(pages[0])).toContain("1 / 4");
    expect(pageText(pages[1])).toContain("01");
    expect(pageText(pages[3])).toContain("Source: AgentBench");
    expect(pageText(pages[3])).toContain("4 / 4");
    expect(pages.every((p) => pageText(p).includes("Ankit"))).toBe(true);
  });

  it.each(["flow", "compare", "list", "stat", "quote"] as const)("a %s is one page with all its words, inside the frame", (kind) => {
    const items =
      kind === "compare"
        ? [{ title: "Demo", body: "clean data\nhappy path" }, { title: "Production", body: "messy data\nexceptions" }]
        : kind === "stat"
          ? [{ title: "41%", body: "of tasks completed end to end" }]
          : kind === "quote"
            ? [{ title: "The paper", body: "Failures cluster around exception handling." }]
            : slides;
    for (const platform of ["linkedin", "x"] as const) {
      const pages = layoutVisual(visual({ kind, items }), { platform, name: "Ankit", measure });
      expect(pages).toHaveLength(1);
      const text = pageText(pages[0]);
      for (const it of items) {
        expect(text).toContain(it.title.split(" ")[0]);
        for (const line of it.body.split("\n")) expect(text).toContain(line.split(" ")[0]);
      }
      for (const p of texts(pages[0])) {
        expect(p.x).toBeGreaterThanOrEqual(0);
        expect(p.x).toBeLessThanOrEqual(pages[0].w);
        expect(p.y).toBeGreaterThan(0);
        expect(p.y + p.lh * (p.lines.length - 1)).toBeLessThanOrEqual(pages[0].h);
      }
    }
  });

  it("a flow on X with five steps wraps into two rows joined by arrows", () => {
    const five = [...slides, { title: "Four", body: "" }, { title: "Five", body: "" }];
    const [page] = layoutVisual(visual({ kind: "flow", items: five }), { platform: "x", name: "", measure });
    const boxes = page.prims.filter((p) => p.t === "rect" && p.w > 200);
    expect(new Set(boxes.map((b) => (b as { y: number }).y)).size).toBe(2);
    expect(page.prims.filter((p) => p.t === "path" && p.fill).length).toBe(4); // one arrowhead between each pair
  });
});

describe("svg", () => {
  it("escapes the text and keeps the page size", () => {
    const [page] = layoutVisual(visual({ kind: "stat", title: "R&D <budgets>", items: [{ title: "41%", body: `"Quoted" & 'single'` }] }), { platform: "x", name: "A&B", measure });
    const svg = pageToSvg(page);
    expect(svg.startsWith("<svg")).toBe(true);
    expect(svg).toContain(`width="1600" height="900"`);
    expect(svg).toContain("R&amp;D &lt;budgets&gt;");
    expect(svg).toContain("&quot;Quoted&quot; &amp; &#39;single&#39;");
    expect(svg).not.toMatch(/<budgets>/);
    expect(new DOMParser().parseFromString(svg, "image/svg+xml").querySelector("parsererror")).toBeNull();
  });
});

describe("buildPdf", () => {
  const latin1 = (bytes: Uint8Array) => Array.from(bytes, (b) => String.fromCharCode(b)).join("");

  it("writes one page per image with a valid cross-reference table", () => {
    const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0xff, 0xd9]);
    const pdf = latin1(buildPdf([{ jpeg, width: 1080, height: 1350 }, { jpeg, width: 1080, height: 1350 }]));
    expect(pdf.startsWith("%PDF-1.4")).toBe(true);
    expect(pdf).toContain("/Type /Pages /Kids [3 0 R 6 0 R] /Count 2");
    expect(pdf).toContain("/MediaBox [0 0 540 675]");
    expect(pdf).toContain("/Filter /DCTDecode /Length 8");
    const xrefAt = Number(/startxref\n(\d+)/.exec(pdf)![1]);
    expect(pdf.slice(xrefAt, xrefAt + 4)).toBe("xref");
    const entries = pdf.slice(xrefAt).split("\n").slice(3, 3 + 8);
    for (const [i, entry] of entries.entries()) {
      const offset = Number(entry.slice(0, 10));
      expect(pdf.slice(offset, offset + `${i + 1} 0 obj`.length)).toBe(`${i + 1} 0 obj`);
    }
    expect(pdf.trimEnd().endsWith("%%EOF")).toBe(true);
  });
});

describe("visual events", () => {
  it("a request shows the visual being drawn; his edits are kept against the visual they belong to", () => {
    const base = visual({ kind: "list", items: slides3(), created_at: "2026-09-28T06:00:00Z", sources: [0], unsourced: [] });
    const c = card({ visual: base });
    const { desk: out } = applyEvents(desk({ cards: [c] }), [
      event("card.visual", { card_id: c.id, kind: "flow", note: "five steps" }),
      event("card.edit", { card_id: c.id, text: "The draft text.", visual: { kind: "list", title: "Mine", items: [{ title: "a", body: "" }], alt_text: "" } }),
    ]);
    const next = out.cards![0];
    expect(next.work).toMatchObject({ kind: "visual", visual_kind: "flow", note: "five steps" });
    expect(next.working?.visual).toMatchObject({ title: "Mine", created_at: base.created_at, sources: [0] });
  });

  it("the demo draws a visual from the post", () => {
    const c = card({ platform: "x", format: "x_single", draft: { text: "The best agent completed 41% of tasks. Exceptions broke the rest.", posts: [] } });
    expect(demoVisual(c, "auto", "2026-09-28T06:00:00Z")).toMatchObject({ kind: "stat", items: [{ title: "41%" }] });
    const out = processDemoEvents(desk({ cards: [c] }), [event("card.visual", { card_id: c.id, kind: "flow", note: "" })]);
    expect(out.cards![0].visual?.kind).toBe("flow");
    expect(out.cards![0].visual?.items?.length).toBeGreaterThanOrEqual(3);
    expect(out.cards![0].work).toBeNull();
  });
});

function slides3() {
  return [
    { title: "One", body: "" },
    { title: "Two", body: "" },
    { title: "Three", body: "" },
  ];
}
