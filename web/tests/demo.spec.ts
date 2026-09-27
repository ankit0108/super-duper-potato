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
  await page.getByRole("button", { name: "Draft from my answers" }).click();
  await expect(page.getByRole("textbox", { name: "LinkedIn post" })).toHaveValue(new RegExp(answer.slice(0, 30)));
});

test("skip a card from the board with a reason", async ({ page }) => {
  const tile = todaySection(page).locator("[data-tile]").nth(1);
  const title = (await tile.locator("h3").textContent())!;
  await tile.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("menuitem", { name: /^Wrong timing/ }).click();
  await expect(page.getByText("Skipped. The ranker will learn from this.")).toBeVisible();
  await expect(todaySection(page).getByText(title, { exact: true })).toHaveCount(0);
  await expect(doneSection(page).getByText("Wrong timing")).toBeVisible();
});

test("ask for a topic and get drafts back", async ({ page }) => {
  await page.goto("/#/requests");
  await page.getByLabel("Topic").fill("Evals for agentic RPA");
  await page.getByRole("button", { name: "Search and draft" }).click();
  await expect(page.getByText(/On it\. Searching beyond the daily sources/)).toBeVisible();
  await expect(page.getByText("Evals for agentic RPA: the practical takeaway").first()).toBeVisible();
});

test("record a stance", async ({ page }) => {
  await page.goto("/#/stances");
  const first = page.locator("article").first();
  await first.getByRole("radio").first().click();
  await expect(page.getByText("Stance saved.")).toBeVisible();
  await expect(first.getByText("Stance recorded")).toBeVisible();
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
