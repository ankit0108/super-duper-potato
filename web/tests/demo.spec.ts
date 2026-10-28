// End to end in demo mode, on desktop and a phone (see playwright.config.ts). The demo data comes from
// `pbs demo` (npm run demo-data): the real pipeline's output, so these tests also catch contract drift.
import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

const PAGES: Array<[string, RegExp]> = [
  ["/studio", /^Studio$/],
  ["/requests", /^Requests$/],
  ["/stances", /^Stances$/],
  ["/metrics", /^Metrics$/],
  ["/insights", /^Insights$/],
  ["/sources", /^Sources$/],
  ["/history", /^History$/],
  ["/system", /^System$/],
  ["/settings", /^Settings$/],
];

async function openDemo(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore the demo first" }).click();
  await expect(page.getByRole("heading", { name: /Today's picks/ })).toBeVisible();
}

const todaySection = (page: Page) => page.locator("section", { has: page.locator("#sec-today") });
const doneSection = (page: Page) => page.locator("section", { has: page.locator("#sec-done") });

async function noSidewaysScroll(page: Page) {
  const [scroll, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scroll, "page scrolls sideways").toBeLessThanOrEqual(width);
}

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  (page as Page & { errors: string[] }).errors = errors;
  await openDemo(page);
});

test.afterEach(async ({ page }) => {
  expect((page as Page & { errors: string[] }).errors, "console errors").toEqual([]);
});

test("the board shows today's set in rank order, this week's cards and what's done", async ({ page }) => {
  await expect(page.getByText(/Delivered \d{1,2}:\d{2}/)).toBeVisible();
  await expect(todaySection(page).locator("[data-tile]")).toHaveCount(15);
  await expect(page.getByRole("heading", { name: /This week/ })).toBeVisible();
  await expect(doneSection(page).getByText("Already covered")).toBeVisible();
  await noSidewaysScroll(page);
});

test("edit a draft, swap the opening and mark it posted", async ({ page }) => {
  await todaySection(page).locator("[data-tile]").first().click();
  const editor = page.getByRole("textbox", { name: "LinkedIn post" });
  await expect(editor).toBeVisible();
  await page.getByRole("button", { name: "Use opening 2" }).click();
  await editor.press("End");
  await editor.pressSequentially(" Worth watching.");
  await page.getByRole("button", { name: "Posted", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Mark as posted" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Mark posted" }).click();
  await expect(page.getByText(/Posted\. You changed \d+% of the draft/)).toBeVisible();

  await page.goto("/#/");
  await expect(doneSection(page).getByText("Posted", { exact: true })).toBeVisible();
  await expect(todaySection(page).locator("[data-tile]")).toHaveCount(14);
  await page.goto("/#/metrics");
  await expect(page.getByRole("button", { name: "Add numbers" }).first()).toBeVisible();
});

test("answer interview questions and get a draft built from the answers", async ({ page }) => {
  await page.getByRole("article", { name: "LinkedIn card: Testing an agent on messy data" }).getByRole("button", { name: "Answer" }).click();
  const answer = "We ran an agent on last quarter's messiest invoices and it stalled on duplicates.";
  await page.getByPlaceholder("A sentence or two is enough. Type or dictate.").first().fill(answer);
  await page.getByRole("button", { name: "Draft from my answers + sources" }).click();
  await expect(page.getByRole("textbox", { name: "LinkedIn post" })).toHaveValue(new RegExp(answer.slice(0, 30)));
});

test("a card with questions arrives drafted from sources; the questions are optional", async ({ page }) => {
  const tile = page.getByRole("article", { name: /LinkedIn card: UiPath adds agentic orchestration/ });
  await expect(tile.getByText("2 optional questions")).toBeVisible();
  await tile.getByRole("button", { name: "Open" }).click();
  await expect(page.getByRole("textbox", { name: "LinkedIn post" })).not.toHaveValue("");
  await page.getByRole("button", { name: /Make it yours/ }).click();
  const answer = "We had to route every unmatched invoice to a person before the agent could close anything.";
  await page.getByPlaceholder(/Optional\. A sentence or two/).first().fill(answer);
  await page.getByRole("button", { name: "Draft from my answers + sources" }).click();
  await expect(page.getByRole("textbox", { name: "LinkedIn post" })).toHaveValue(new RegExp(answer.slice(0, 30)));
});

test("a card waiting for answers can be drafted from sources without answering", async ({ page }) => {
  await page.getByRole("article", { name: "LinkedIn card: Testing an agent on messy data" }).getByRole("button", { name: "Answer" }).click();
  await page.getByRole("button", { name: "Draft from sources only" }).click();
  await expect(page.getByText("Drafting it from recent sources. Takes 1–3 minutes.")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "LinkedIn post" })).toBeVisible();
});

test("skip a card from the board with a reason", async ({ page }) => {
  const tile = todaySection(page).locator("[data-tile]").nth(1);
  const name = (await tile.getAttribute("aria-label"))!; // "LinkedIn card: …" (a cross-post can share the title)
  await tile.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("menuitem", { name: /^Wrong timing/ }).click();
  await expect(page.getByText("Skipped. No penalty: it was only the timing.")).toBeVisible();
  await expect(todaySection(page).getByRole("article", { name, exact: true })).toHaveCount(0);
  await expect(doneSection(page).getByText("Wrong timing")).toBeVisible();
});

test("skipping for another reason asks why, and the reason shows in what the ranking learns from", async ({ page }) => {
  const tile = todaySection(page).locator("[data-tile]").nth(2);
  const title = (await tile.locator("h3").textContent())!;
  await tile.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("menuitem", { name: /^Other…/ }).click();
  const dialog = page.getByRole("dialog", { name: "Why skip it?" });
  const confirm = dialog.getByRole("button", { name: "Skip with this reason" });
  await expect(confirm).toBeDisabled();
  const why = "Industrial automation, not my focus: I mean automating business processes";
  await dialog.getByRole("textbox").fill(why);
  await confirm.click();
  await expect(page.getByText("Skipped. Your reason feeds tomorrow's ranking and the weekly review.")).toBeVisible();
  await expect(todaySection(page).getByText(title, { exact: true })).toHaveCount(0);
  await page.goto("/#/insights?tab=learning");
  await expect(page.getByRole("heading", { name: "Your recent feedback" })).toBeVisible();
  await expect(page.getByText(`“${why}”`)).toBeVisible();
});

test("“Other…” asks why on a tap, from the card page too", async ({ page }, testInfo) => {
  const press = (l: ReturnType<Page["locator"]>) => (testInfo.project.name === "mobile" ? l.tap() : l.click());
  await press(todaySection(page).locator("[data-tile]").nth(1).locator("h3"));
  const title = (await page.getByRole("heading", { level: 1 }).textContent())!;
  await press(page.getByRole("button", { name: "Skip", exact: true }));
  await press(page.getByRole("menuitem", { name: /^Other…/ }));
  const dialog = page.getByRole("dialog", { name: "Why skip it?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(title)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Skip with this reason" })).toBeDisabled();
  await dialog.getByRole("textbox").fill("Too close to yesterday's post");
  await press(dialog.getByRole("button", { name: "Skip with this reason" }));
  await expect(page.getByText("Skipped. Your reason feeds tomorrow's ranking and the weekly review.")).toBeVisible();
  await expect(page.getByText("Other — Too close to yesterday's post")).toBeVisible();
});

test("get fresh posts: a new set lands on top of today's picks", async ({ page }) => {
  const firstX = (await todaySection(page).getByRole("article", { name: /^X card:/ }).first().getAttribute("aria-label"))!;
  await page.getByRole("button", { name: "Get fresh posts" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Get fresh posts" });
  await dialog.getByRole("radio", { name: "X", exact: true }).click();
  await dialog.getByRole("radio", { name: "2", exact: true }).click();
  await dialog.getByRole("button", { name: "Get 2 fresh posts" }).click();
  await expect(page.getByText("Getting 2 fresh posts. They land on top of Today's picks as they're drafted: the first in a minute or two.")).toBeVisible();
  await expect(page.getByText("2 new posts are ready on the board.")).toBeVisible();
  await expect(todaySection(page).getByText(/^Fresh set/)).toBeVisible();
  const xTiles = todaySection(page).getByRole("article", { name: /^X card:/ });
  await expect(xTiles.nth(2)).toHaveAttribute("aria-label", firstX); // the morning set now follows the fresh one
  await noSidewaysScroll(page);
});

test("a newer deployed desk is noticed and offered as a reload, and System shows the version", async ({ page }) => {
  const built = await (await page.request.get("/version.json")).json();
  expect(built.id).toMatch(/^[\w-]+$/);
  await page.goto("/#/system");
  await expect(page.getByText(new RegExp(`^Desk version ${built.id.split("-")[0]}`))).toBeVisible();
  await expect(page.getByText(/The desk was updated/)).toHaveCount(0);
  await page.route("**/version.json*", (route) => route.fulfill({ json: { id: "a-newer-build", at: "2026-10-01T09:00:00Z" } }));
  await page.reload();
  await expect(page.getByText("The desk was updated. Reload to get the new version (your edits are kept).")).toBeVisible();
});

type DemoCard = { title: string; platform: string; status: string; delivery_id?: string | null; post_type?: string | null; alternatives?: string[]; trending?: { on: string } | null; llm?: { edit?: { kept?: boolean; before?: number } | null } | null };
/** The demo's own data (the pipeline's output), to find a card by what happened to it rather than by its title. */
const demoDesk = () => JSON.parse(readFileSync("public/demo/desk.json", "utf-8")) as { delivery?: { id: string }; cards: DemoCard[] };

test("writing that sounds like AI is flagged as you type, and the editor pass shows what it fixed", async ({ page }) => {
  // A LinkedIn card in today's set whose draft came back with one tell ("Here's why:"), which the editor pass took out.
  const desk = demoDesk();
  const fixed = desk.cards.find((c) => c.platform === "linkedin" && c.status === "suggested" && c.delivery_id === desk.delivery?.id && c.llm?.edit?.kept && c.llm.edit.before === 1);
  expect(fixed, "the demo has a LinkedIn card the editor improved").toBeTruthy();
  await todaySection(page).getByRole("article", { name: `LinkedIn card: ${fixed!.title}` }).click();
  await page.getByRole("tab", { name: "Details" }).click();
  // The side panel is in the page twice (phone and desktop layouts): look at the one on screen.
  await expect(page.getByText("Fixed 1 of 1 AI tell (groq)").filter({ visible: true })).toBeVisible();
  const editor = page.getByRole("textbox", { name: "LinkedIn post" });
  await editor.press("ControlOrMeta+End");
  await editor.pressSequentially("\n\nIt's not about speed, it's about trust.");
  await page.getByRole("tab", { name: "Checks" }).click();
  const live = page.locator("[aria-live=polite]").filter({ hasText: "Live checks", visible: true });
  await expect(live.getByText("Sounds like AI")).toBeVisible();
  await expect(live.getByText(/Contrast framing .+: “It's not about speed, it's about trust\.”/)).toBeVisible();
  // The pipeline's own checks flag none: the editor pass took the draft's one tell out.
  await expect(page.getByText("Sounds like AI", { exact: true }).filter({ visible: true })).toHaveCount(1);
});

test("a Bihar story from history arrives as its own kind of X post, not as news", async ({ page }) => {
  await todaySection(page).getByRole("article", { name: /^X card: Vikramashila/ }).click();
  await expect(page.getByText("Story, history to now").filter({ visible: true }).first()).toBeVisible();
  await expect(page.getByText("A story from history to now, not today's news.").filter({ visible: true }).first()).toBeVisible();
  await page.goto("/#/sources");
  await page.getByRole("tab", { name: /^Affairs/ }).click();
  await expect(page.getByText("Wikipedia: Bihar, history to now").filter({ visible: true }).first()).toBeVisible();
});

test("funny posts, quotes and thoughts arrive with a badge saying which kind", async ({ page }) => {
  const desk = demoDesk();
  const today = desk.cards.filter((c) => c.delivery_id === desk.delivery?.id && c.status === "suggested");
  // Funny posts come from real stories now, written in the writers' room (the generic premises are off).
  const funny = today.find((c) => c.platform === "linkedin" && c.post_type === "funny_take" && (c.alternatives?.length ?? 0) > 0);
  const quote = today.find((c) => c.platform === "x" && c.post_type === "quote");
  const thought = today.find((c) => c.platform === "x" && c.post_type === "thought");
  expect(funny && quote && thought, "the demo's morning has a funny LinkedIn post, a quote and a thought").toBeTruthy();
  const funnyTile = todaySection(page).getByRole("article", { name: `LinkedIn card: ${funny!.title}` });
  await expect(funnyTile.getByText("Tech humour")).toBeVisible();
  await expect(funnyTile.getByText("Funny take")).toBeVisible();
  await expect(todaySection(page).getByRole("article", { name: `X card: ${thought!.title}` }).getByText("Thought", { exact: true })).toBeVisible();
  const quoteTile = todaySection(page).getByRole("article", { name: `X card: ${quote!.title}` });
  await expect(quoteTile.getByText("Quote", { exact: true })).toBeVisible();
  await quoteTile.click();
  await expect(page.getByText("A quote, found word for word on Wikiquote; not news.").filter({ visible: true }).first()).toBeVisible();
  await page.goto("/#/sources");
  await page.getByRole("tab", { name: /^Ideas/ }).click();
  await expect(page.getByText("Wikiquote: quotes worth sharing").filter({ visible: true }).first()).toBeVisible();
});

test("a quote that no longer matches its source is flagged as you type", async ({ page }) => {
  const desk = demoDesk();
  const quote = desk.cards.find((c) => c.delivery_id === desk.delivery?.id && c.status === "suggested" && c.platform === "x" && c.post_type === "quote");
  await todaySection(page).getByRole("article", { name: `X card: ${quote!.title}` }).click();
  const editor = page.getByRole("textbox", { name: "Single post text" });
  const text = await editor.inputValue();
  const altered = text.replace(/\u201c(\S+) /, "\u201cA $1 ");
  expect(altered, "the draft opens with the quote").not.toBe(text);
  await page.getByRole("tab", { name: "Checks" }).click();
  const live = page.locator("[aria-live=polite]").filter({ hasText: "Live checks", visible: true });
  await expect(live.getByText(/Quote changed/)).toHaveCount(0);
  await editor.fill(altered);
  await expect(live.getByText("Quote changed: not word for word in the source")).toBeVisible();
});

test("Insights shows AI tells per draft before and after the editor pass", async ({ page }) => {
  await page.goto("/#/insights?tab=voice");
  await expect(page.getByText("Sounds like AI, by week")).toBeVisible();
  await expect(page.getByText("Drafts the editor improved (30 days)")).toBeVisible();
  await expect(page.getByText("Most common tell (30 days)")).toBeVisible();
  await expect(page.getByRole("img", { name: "Average AI tells per draft as written and as shown, by week" })).toBeVisible();
  await noSidewaysScroll(page);
});

test("edit an opening, write your own, and they go into the draft", async ({ page }) => {
  await todaySection(page).locator("[data-tile]").first().click();
  const editor = page.getByRole("textbox", { name: "LinkedIn post" });
  await page.getByRole("button", { name: "Use opening 1" }).click();
  await page.getByRole("button", { name: "Edit opening 1" }).click();
  await page.getByRole("textbox", { name: "Edit opening 1" }).fill("An opening in my own words.");
  await page.getByRole("button", { name: "Save opening" }).click();
  await expect(editor).toHaveValue(/^An opening in my own words\./);
  await page.getByRole("button", { name: "Write my own opening" }).click();
  await page.getByRole("textbox", { name: "Your own opening" }).fill("Last week I rebuilt a bot from scratch.");
  await page.getByRole("button", { name: "Add and use" }).click();
  await expect(editor).toHaveValue(/^Last week I rebuilt a bot from scratch\./);
  await expect(page.getByText("Your own")).toBeVisible();
});

test("hashtags are suggested as chips, and the ones you keep go out at the end of the post", async ({ page }) => {
  await todaySection(page).locator("[data-tile]").first().click();
  const tags = page.getByRole("group", { name: "Hashtags" });
  const chips = tags.locator("button[aria-pressed]");
  await expect(chips.first()).toBeVisible();
  expect(await chips.count()).toBeGreaterThanOrEqual(3);
  const dropped = (await chips.first().textContent())!.trim();
  await chips.first().click();
  await expect(chips.first()).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("textbox", { name: "Add a hashtag" }).fill("process mining");
  await page.getByRole("button", { name: "Add hashtag" }).click();
  await expect(tags.getByRole("button", { name: "#ProcessMining", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Copy the first comment" })).toBeVisible();
  await page.getByRole("button", { name: "Posted", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Mark as posted" });
  const lastLine = (await dialog.getByRole("textbox", { name: "Final text" }).inputValue()).trim().split("\n").pop()!.split(" ");
  expect(lastLine).toContain("#ProcessMining");
  expect(lastLine).not.toContain(dropped);
  await dialog.getByRole("button", { name: "Mark posted" }).click();
  await expect(page.getByText("Posted. You changed 0% of the draft.")).toBeVisible();
});

test.describe("copying and sharing", () => {
  // Record what the desk copies and shares, instead of reaching the real clipboard or share sheet.
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      const w = window as unknown as { copied: string[]; shared: string[] };
      w.copied = [];
      w.shared = [];
      Object.defineProperty(navigator, "clipboard", { value: { writeText: async (t: string) => void w.copied.push(t) }, configurable: true });
      Object.defineProperty(navigator, "share", { value: async (d: ShareData) => void w.shared.push(d.text ?? ""), configurable: true });
    });
    await page.reload();
    await expect(page.getByRole("heading", { name: /Today's picks/ })).toBeVisible();
  });
  const recorded = (page: Page, key: "copied" | "shared") => page.evaluate((k) => (window as unknown as Record<string, string[]>)[k], key);

  test("Copy draft copies just the draft, without the hashtags", async ({ page }) => {
    await todaySection(page).getByRole("article", { name: /^LinkedIn card:/ }).first().click();
    const editor = page.getByRole("textbox", { name: "LinkedIn post" });
    const draft = await editor.inputValue();
    await expect(page.getByRole("group", { name: "Hashtags" }).locator("button[aria-pressed=true]").first()).toBeVisible();
    await page.getByRole("button", { name: "Copy draft" }).click();
    await expect(page.getByText("Draft copied")).toBeVisible();
    expect(await recorded(page, "copied")).toEqual([draft]);
    // The bar's Copy is the whole post, with the chosen hashtags at the end.
    await page.getByRole("button", { name: "Copy", exact: true }).click();
    const post = (await recorded(page, "copied"))[1];
    expect(post.startsWith(draft.trimEnd())).toBe(true);
    expect(post.slice(draft.trimEnd().length)).toMatch(/^\n\n#\w+/);
  });

  test("Copy draft on a thread copies the posts without numbers", async ({ page }) => {
    await todaySection(page).getByRole("article", { name: /^X card:/ }).filter({ hasText: "Thread" }).first().click();
    const posts = await page.getByRole("textbox", { name: /^Post \d+ of \d+$/ }).evaluateAll((els) => els.map((e) => (e as HTMLTextAreaElement).value));
    await page.getByRole("checkbox", { name: "Add 1/n when copying" }).check();
    await page.getByRole("button", { name: "Copy draft" }).click();
    expect(await recorded(page, "copied")).toEqual([posts.join("\n\n")]);
  });

  test("Open LinkedIn hands the post to LinkedIn's composer: the share sheet on a phone, the web composer otherwise", async ({ page }, testInfo) => {
    await todaySection(page).getByRole("article", { name: /^LinkedIn card:/ }).first().click();
    const draft = await page.getByRole("textbox", { name: "LinkedIn post" }).inputValue();
    if (testInfo.project.name === "mobile") {
      await page.getByRole("button", { name: "Open LinkedIn" }).tap();
      await expect(page.getByText("Sent to LinkedIn. Post it there, then come back and tap Posted.")).toBeVisible();
      const [shared] = await recorded(page, "shared");
      expect(shared.startsWith(draft.trimEnd())).toBe(true);
      expect(await recorded(page, "copied")).toEqual([shared]); // copied too, in case LinkedIn opens empty
    } else {
      const link = page.getByRole("link", { name: "Open LinkedIn" });
      const href = (await link.getAttribute("href"))!;
      expect(href.startsWith("https://www.linkedin.com/feed/?shareActive=true&text=")).toBe(true);
      expect(decodeURIComponent(href.split("&text=")[1]).startsWith(draft.trimEnd())).toBe(true);
    }
  });
});

test("move a card to the other platform from the Skip menu", async ({ page }) => {
  const tile = todaySection(page).getByRole("article", { name: /^X card:/ }).first();
  const title = (await tile.locator("h3").textContent())!;
  await tile.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("menuitem", { name: /^Move to LinkedIn instead/ }).click();
  await expect(page.getByText(/^Moving it to LinkedIn/)).toBeVisible();
  await expect(page.getByText(/^Your LinkedIn version of “.+” is ready\.$/)).toBeVisible();
  await expect(todaySection(page).getByRole("article", { name: `LinkedIn card: ${title}` }).getByText("Cross-post")).toBeVisible();
  await expect(doneSection(page).getByRole("listitem").filter({ hasText: title }).getByText("Wrong platform")).toBeVisible();
  await page.goto("/#/insights?tab=learning");
  await expect(page.getByRole("listitem").filter({ hasText: title }).getByText("Moved to LinkedIn")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Cross-posts (last 30 days)" })).toBeVisible();
});

test("make an X version of a LinkedIn card, and the two link to each other", async ({ page }) => {
  await todaySection(page).locator("[data-tile]").first().click();
  // The card's own heading, once its page is open (not the board's, while it's still on screen).
  await expect(page).toHaveURL(/#\/card\//);
  await expect(page.getByRole("button", { name: "Also for X" })).toBeVisible();
  const title = (await page.getByRole("heading", { level: 1 }).textContent())!;
  await page.getByRole("button", { name: "Also for X" }).click();
  const dialog = page.getByRole("dialog", { name: "Make an X version" });
  await dialog.getByLabel("Format on X").selectOption("x_thread");
  await dialog.getByRole("button", { name: "Make the X version" }).click();
  await expect(page.getByText(/^Making the X version/)).toBeVisible();
  const ready = page.locator("[aria-live=polite] > div").filter({ hasText: /^Your X version of “.+” is ready\./ });
  await ready.getByRole("button", { name: "Open" }).click();
  await expect(page.getByText(/Cross-post of the LinkedIn card/)).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
  await expect(page.getByRole("textbox", { name: /^Post 1 of/ })).toBeVisible();
});

test("the platform guide drafts follow, and researched changes wait for approval", async ({ page }) => {
  await page.goto("/#/insights?tab=playbook");
  await expect(page.getByRole("heading", { name: "What works on each platform" })).toBeVisible();
  await expect(page.getByText(/Latest research/)).toBeVisible();
  await noSidewaysScroll(page);
  await page.getByRole("button", { name: "Research now" }).click();
  await expect(page.getByText("Research requested. Proposed changes appear under Proposals after the run.")).toBeVisible();
  await page.goto("/#/insights?tab=proposals");
  const proposal = page.getByRole("listitem").filter({ hasText: "LinkedIn guide: update" });
  await expect(proposal.getByText("Based on:")).toBeVisible();
  await expect(proposal.getByRole("link", { name: /What creators are seeing in LinkedIn's feed/ })).toBeVisible();
  await noSidewaysScroll(page);
  await proposal.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved: it applies on the next run.")).toBeVisible();
});

test("a card's carousel: flip through it, download the PDF and a slide", async ({ page }) => {
  await page.getByRole("article", { name: /^LinkedIn card: AgentBench/ }).click();
  const panel = page.getByRole("region", { name: "Visual" });
  await expect(panel.getByRole("img")).toHaveAttribute("alt", /Carousel: 41% end to end/);
  // Its cover has an AI picture behind it (made by the pipeline's demo image service); the words are drawn on top.
  await expect(panel.locator("h3").getByText("AI background", { exact: true })).toBeVisible();
  await expect(panel.getByText(/^Picture: AI-generated \(cloudflare, flux-2-klein-4b\)/)).toBeVisible();
  await expect.poll(async () => decodeURIComponent((await panel.getByRole("img").getAttribute("src")) ?? "")).toContain("<image href=\"data:image/png;base64,");
  await expect(panel.getByText("Slide 1 of 6")).toBeVisible();
  await panel.getByRole("button", { name: "Next slide" }).click();
  await expect(panel.getByText("Slide 2 of 6")).toBeVisible();
  const [pdf] = await Promise.all([page.waitForEvent("download"), panel.getByRole("button", { name: "Download PDF" }).click()]);
  expect(pdf.suggestedFilename()).toMatch(/\.pdf$/);
  const pdfBytes = readFileSync((await pdf.path())!);
  expect(pdfBytes.subarray(0, 8).toString("latin1")).toBe("%PDF-1.4");
  expect(pdfBytes.toString("latin1")).toContain("/Count 6");
  const [png] = await Promise.all([page.waitForEvent("download"), panel.getByRole("button", { name: "Download this slide (PNG)" }).click()]);
  expect(png.suggestedFilename()).toMatch(/-2\.png$/);
  expect(readFileSync((await png.path())!).subarray(1, 4).toString("latin1")).toBe("PNG");
});

test("an AI image for a post: made by the image service, headline drawn on it, downloaded as PNG", async ({ page }) => {
  await todaySection(page).getByRole("article", { name: /^LinkedIn card:/ }).nth(1).click();
  const panel = page.getByRole("region", { name: "Visual" });
  await panel.getByLabel("Kind").selectOption("image");
  await panel.getByRole("button", { name: "Create visual" }).click();
  await expect(page.getByText(/^Making an AI image for this post/)).toBeVisible();
  await expect(page.getByText(/^The visual for “.+” is ready\.$/)).toBeVisible();
  await expect(panel.locator("h3").getByText("AI image", { exact: true })).toBeVisible();
  await expect(panel.getByRole("img")).toHaveAttribute("alt", /^AI-generated illustration/);
  await expect(panel.getByText(/^Picture: AI-generated/)).toBeVisible();
  const [png] = await Promise.all([page.waitForEvent("download"), panel.getByRole("button", { name: "Download PNG" }).click()]);
  expect(readFileSync((await png.path())!).subarray(1, 4).toString("latin1")).toBe("PNG");
});

test("a carousel can get an AI background", async ({ page }) => {
  await todaySection(page).getByRole("article", { name: /^X card:/ }).first().click();
  const panel = page.getByRole("region", { name: "Visual" });
  await panel.getByLabel("Kind").selectOption("carousel");
  await panel.getByRole("checkbox", { name: "Add an AI background" }).check();
  await panel.getByRole("button", { name: "Create visual" }).click();
  await expect(page.getByText(/^Making a carousel with an AI background for this post/)).toBeVisible();
  await expect(panel.locator("h3").getByText("AI background", { exact: true })).toBeVisible();
});

test.describe("without an image service", () => {
  // The service worker would answer desk.json itself, out of this test's reach.
  test.use({ serviceWorkers: "block" });

  test("the AI options say what to add instead of failing later", async ({ page }) => {
    await page.route("**/demo/desk.json", async (route) => {
      const desk = await (await route.fetch()).json();
      await route.fulfill({ json: { ...desk, images: { available: false, providers: [], used_today: 0, daily_limit: 20 } } });
    });
    await page.goto("/"); // a fresh load, still in demo mode
    await todaySection(page).getByRole("article", { name: /^X card:/ }).nth(1).click();
    const panel = page.getByRole("region", { name: "Visual" });
    await expect(panel.getByRole("option", { name: "AI image (set up first)" })).toBeDisabled();
    await expect(panel.getByText(/AI images need an image service: add the free CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN secrets/)).toBeVisible();
    await expect(panel.getByRole("checkbox", { name: /Add an AI background/ })).not.toBeChecked();
  });
});

test("draw a flowchart for a post, edit its words and post it with the visual", async ({ page }) => {
  await todaySection(page).getByRole("article", { name: /^X card:/ }).first().click();
  const panel = page.getByRole("region", { name: "Visual" });
  await panel.getByLabel("Kind").selectOption("flow");
  await panel.getByRole("button", { name: "Create visual" }).click();
  await expect(page.getByText(/^Making a flowchart for this post/)).toBeVisible();
  await expect(page.getByText(/^The visual for “.+” is ready\.$/)).toBeVisible();
  await expect(panel.locator("h3").getByText("Flowchart", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "Edit text" }).click();
  await panel.getByLabel("Headline").fill("Three corridors, five steps");
  await panel.getByRole("button", { name: "Save visual" }).click();
  await expect.poll(async () => decodeURIComponent((await panel.getByRole("img").getAttribute("src")) ?? "")).toContain("Three corridors, five steps");
  await page.getByRole("button", { name: "Posted", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Mark as posted" });
  await expect(dialog.getByRole("checkbox", { name: /Posted with the visual \(flowchart\)/ })).toBeChecked();
  await dialog.getByRole("button", { name: "Mark posted" }).click();
  await expect(page.getByText(/^Posted\./)).toBeVisible();
  await page.goto("/#/insights?tab=learning");
  await expect(page.getByRole("heading", { name: "Posts with a visual (last 90 days)" })).toBeVisible();
});

test("ask for a topic and get drafts back", async ({ page }) => {
  await page.goto("/#/requests");
  await page.getByLabel("Topic").fill("Evals for agentic RPA");
  await page.getByRole("button", { name: "Search and draft" }).click();
  await expect(page.getByText(/On it\. Searching beyond the daily sources/)).toBeVisible();
  await expect(page.getByText("Evals for agentic RPA: the practical takeaway").first()).toBeVisible();
  await expect(page.getByText("Understood as:").first()).toBeVisible();
});

test("record a stance", async ({ page }) => {
  await page.goto("/#/stances");
  const first = page.locator("article").first();
  await first.getByRole("radio").first().click();
  await expect(page.getByText("Stance saved.")).toBeVisible();
  await expect(first.getByText("Stance recorded")).toBeVisible();
});

test("a stance in your own words shows as saved, and stays after leaving the page", async ({ page }) => {
  await page.goto("/#/stances");
  const first = page.locator("article").first();
  const issue = (await first.locator("h3").textContent())!;
  await first.getByRole("button", { name: "Write my own" }).click();
  const mine = "Keep the goal, but fix enforcement before judging the policy.";
  await first.getByRole("textbox", { name: "Your own stance" }).fill(mine);
  await first.getByRole("button", { name: "Save my wording" }).click();
  await expect(page.getByText("Your stance is saved in your own words.")).toBeVisible();
  await expect(first.getByRole("textbox", { name: "Your own stance" })).toHaveCount(0);
  await expect(first.getByText(mine)).toBeVisible();
  await page.goto("/#/");
  await page.goto("/#/stances");
  const again = page.getByRole("article", { name: `Stance: ${issue}` });
  await expect(again.getByText(mine)).toBeVisible();
  await expect(again.getByRole("button", { name: "Edit my wording" })).toBeVisible();
});

test("confirm an extracted number and add numbers by hand", async ({ page }) => {
  await page.goto("/#/metrics");
  await expect(page.getByRole("heading", { name: /Check 1 extracted number/ })).toBeVisible();
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Confirmed.")).toBeVisible();
  await page.getByRole("button", { name: "Add numbers" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Add numbers" });
  await dialog.getByRole("textbox").first().fill("1,234");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Numbers saved. Rewards update on the next run.")).toBeVisible();
});

test("every page renders, with no sideways scrolling", async ({ page }) => {
  for (const [path, heading] of PAGES) {
    await page.goto(`/#${path}`);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await noSidewaysScroll(page);
  }
  await page.goto("/#/");
  await todaySection(page).locator("[data-tile]").first().click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await noSidewaysScroll(page);
});

// A small PNG (a 16x16 square) for picture uploads.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR4nGPQCDhBEmIY1TCqYfhqAAB/t0AQQWrvwQAAAABJRU5ErkJggg==",
  "base64",
);

const studioMessage = (page: Page) => page.getByRole("textbox", { name: "Message the Studio" });

test.describe("Studio", () => {
  test("a picture becomes a LinkedIn post, saved to the board with the picture", async ({ page }) => {
    await page.goto("/#/studio");
    await expect(page.getByRole("heading", { level: 1, name: "Studio" })).toBeVisible();
    await page.locator('input[type="file"][multiple]').setInputFiles({ name: "whiteboard.png", mimeType: "image/png", buffer: PNG });
    await expect(page.getByRole("img", { name: "Picture 1" })).toBeVisible();
    await studioMessage(page).fill("Write a LinkedIn post about this picture.");
    await page.getByRole("button", { name: "Send" }).click();
    const post = page.getByRole("region", { name: "LinkedIn post" });
    await expect(post.getByRole("textbox", { name: "LinkedIn post text" })).toHaveValue(/Whiteboards tell you more/);
    // The picture you sent is picked to post with it; another opening swaps in at the top.
    await expect(post.getByRole("button", { name: "Picture 1, included" })).toHaveAttribute("aria-pressed", "true");
    await post.getByRole("button", { name: /^Use opening: Agents don't fail in demos/ }).click();
    await expect(post.getByRole("textbox", { name: "LinkedIn post text" })).toHaveValue(/^Agents don't fail in demos\. They fail on Tuesdays\./);
    // The chat stays on this device: still there after a reload, with your edit.
    await page.reload();
    await expect(post.getByRole("textbox", { name: "LinkedIn post text" })).toHaveValue(/^Agents don't fail in demos/);
    await post.getByRole("button", { name: "Save to board" }).click();
    await expect(page.getByText("Saved to the board: it's in Today's picks.")).toBeVisible();
    await expect(post.getByText("On the board")).toBeVisible();
    await post.getByRole("link", { name: "Open the card" }).click();
    await expect(page.getByText("From the Studio", { exact: true })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "LinkedIn post" })).toHaveValue(/^Agents don't fail in demos/);
    await expect(page.getByRole("region", { name: "Pictures" }).getByRole("img", { name: "Picture 1" })).toBeVisible();
    await page.goto("/#/");
    await expect(todaySection(page).getByText("From the Studio")).toBeVisible();
  });

  test("a carousel: start from a quick action, flip through it and download the PDF", async ({ page }) => {
    await page.goto("/#/studio");
    await page.getByRole("group", { name: "Quick actions" }).getByRole("button", { name: "Carousel" }).click();
    await expect(studioMessage(page)).toHaveValue("Make a LinkedIn carousel about ");
    await studioMessage(page).pressSequentially("shipping AI agents");
    await page.getByRole("button", { name: "Send" }).click();
    const visual = page.getByRole("region", { name: "Carousel" });
    await expect(visual.getByText("Slide 1 of 6")).toBeVisible();
    await visual.getByRole("button", { name: "Next slide" }).click();
    await expect(visual.getByText("Slide 2 of 6")).toBeVisible();
    const [pdf] = await Promise.all([page.waitForEvent("download"), visual.getByRole("button", { name: "Download PDF" }).click()]);
    expect(readFileSync((await pdf.path())!).toString("latin1")).toContain("/Count 6");
    // Then the post to go with it, saved together.
    await visual.getByRole("button", { name: "Write the post for it" }).click();
    const post = page.getByRole("region", { name: "LinkedIn post" });
    await expect(post.getByRole("combobox", { name: "Visual to save with it" })).toHaveValue(/:/);
  });

  test("Ask Studio from a card, and an idea becomes a draft", async ({ page }) => {
    await page.getByRole("article", { name: /^LinkedIn card: AgentBench/ }).click();
    await page.getByRole("button", { name: "Ask Studio" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Studio" })).toBeVisible();
    await expect(page.getByText(/AgentBench/).first()).toBeVisible();
    await page.getByRole("group", { name: "Quick actions" }).getByRole("button", { name: "Post ideas" }).click();
    const ideas = page.getByRole("region", { name: "Post ideas" });
    await expect(ideas.getByRole("listitem")).toHaveCount(4);
    await ideas.getByRole("button", { name: "Write for LinkedIn" }).first().click();
    await expect(page.getByRole("region", { name: "LinkedIn post" })).toBeVisible();
    await noSidewaysScroll(page);
  });

  test("a post shared from another app opens the Studio, which says why it works", async ({ page }) => {
    // What the service worker keeps when you pick PBS Desk in Android's share sheet (public/sw.js).
    await page.evaluate(async (png) => {
      const cache = await caches.open("pbs-share");
      await cache.put("shared/meta", new Response(JSON.stringify({ title: "", text: "This agent post is everywhere", url: "https://www.linkedin.com/posts/someone_agents", files: 1 })));
      await cache.put("shared/file-0", new Response(Uint8Array.from(atob(png), (c) => c.charCodeAt(0)), { headers: { "content-type": "image/png" } }));
    }, PNG.toString("base64"));
    await page.goto("/#/studio?shared=1");
    await expect(page.getByText("Shared from LinkedIn")).toBeVisible();
    await expect(page.getByRole("img", { name: "Picture 1" })).toBeVisible();
    await page.getByRole("group", { name: "Quick actions" }).getByRole("button", { name: "Why is it working?" }).click();
    await expect(page.getByText("Why it works:")).toBeVisible();
    // Taken once: opening the link again starts empty.
    await page.goto("/#/studio?shared=1");
    await expect(page.getByText("What do you want to post about?")).toBeVisible();
  });
});

test("a funny post from the writers' room: the critic's note, and another version in one tap", async ({ page }) => {
  const desk = demoDesk();
  const funny = desk.cards.find((c) => c.delivery_id === desk.delivery?.id && c.status === "suggested" && c.platform === "linkedin" && (c.alternatives?.length ?? 0) > 0);
  expect(funny, "the demo's morning has a funny post from the writers' room").toBeTruthy();
  await todaySection(page).getByRole("article", { name: `LinkedIn card: ${funny!.title}` }).click();
  const room = page.getByRole("region", { name: "Writers' room" });
  await expect(room.getByText(/Critic's verdict: ok/)).toBeVisible();
  await room.getByRole("button", { name: "Use version 2" }).click();
  await expect(page.getByRole("textbox", { name: "LinkedIn post" })).toHaveValue(funny!.alternatives![0]);
  if (funny!.trending) await expect(page.getByText(/^Trending on /).first()).toBeVisible();
});

test("what's working on LinkedIn and X: the week's conversations in Insights", async ({ page }) => {
  await page.goto("/#/insights?tab=working");
  await expect(page.getByText("What's working on LinkedIn and X")).toBeVisible();
  await expect(page.getByText("AI agents that report work they never did").first()).toBeVisible();
  await expect(page.getByText(/^Why it works:/).first()).toBeVisible();
  await page.goto("/#/sources");
  await page.getByRole("tab", { name: /^Buzz/ }).click();
  await expect(page.getByText("Social pulse: what's working on LinkedIn and X").filter({ visible: true }).first()).toBeVisible();
});
