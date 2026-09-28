// End to end in demo mode, on desktop and a phone (see playwright.config.ts). The demo data comes from
// `pbs demo` (npm run demo-data): the real pipeline's output, so these tests also catch contract drift.
import { expect, test, type Page } from "@playwright/test";

const PAGES: Array<[string, RegExp]> = [
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
  await expect(todaySection(page).locator("[data-tile]")).toHaveCount(8);
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
  await expect(todaySection(page).locator("[data-tile]")).toHaveCount(7);
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
  await expect(page.getByText("Drafting it from recent sources. About two minutes.")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "LinkedIn post" })).toBeVisible();
});

test("skip a card from the board with a reason", async ({ page }) => {
  const tile = todaySection(page).locator("[data-tile]").nth(1);
  const title = (await tile.locator("h3").textContent())!;
  await tile.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("menuitem", { name: /^Wrong timing/ }).click();
  await expect(page.getByText("Skipped. No penalty: it was only the timing.")).toBeVisible();
  await expect(todaySection(page).getByText(title, { exact: true })).toHaveCount(0);
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
