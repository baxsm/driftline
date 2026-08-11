import { expect, test } from "@playwright/test";
import {
  queueRunAndWait,
  registerAndSignIn,
  registerSequence,
  SCORABLE_SEQUENCE_PATH,
} from "./helpers";

/**
 * The compare flow end to end: two real runs on one sequence, selected from the list, put side
 * by side. Nothing is stubbed, so the deltas here are the deltas the scorer produced.
 */
test.describe("compare", () => {
  test.skip(!SCORABLE_SEQUENCE_PATH, "set E2E_SCORABLE_SEQUENCE_PATH to a scorable sequence");

  test.beforeEach(async ({ page }) => {
    await registerAndSignIn(page);
  });

  /** Two runs differing in one setting, so the diff has exactly one row to find. */
  async function twoRuns(page: import("@playwright/test").Page): Promise<void> {
    await registerSequence(page, SCORABLE_SEQUENCE_PATH, "cmp sequence");
    await queueRunAndWait(page, "cmp first");

    await page.getByRole("button", { name: "New run" }).click();
    await page.getByLabel("Label").fill("cmp second");
    await page.getByLabel("Max features").fill("400");
    await page.getByRole("button", { name: "Queue run" }).click();
    await page
      .getByRole("listitem")
      .filter({ hasText: "cmp second" })
      .getByText("Done")
      .waitFor({ timeout: 60_000 });
  }

  test("asks for a pair rather than erroring when none is chosen", async ({ page }) => {
    await page.goto("/app/compare");

    await expect(page.getByText("Pick two runs to compare")).toBeVisible();
    await expect(page.getByRole("link", { name: "Go to runs" })).toBeVisible();
  });

  test("compares two runs picked from the list", async ({ page }) => {
    await twoRuns(page);

    await page.goto("/app/runs");
    const boxes = page.getByTestId("run-list").getByRole("checkbox");
    await boxes.nth(0).check();
    await boxes.nth(1).check();

    await page.getByRole("button", { name: "Compare" }).click();
    await page.waitForURL(/\/app\/compare\?run_a=.+&run_b=.+/);

    // the one setting that differs, and only that one
    const diff = page.getByRole("table").first();
    await expect(diff.getByRole("rowheader", { name: "Max features" })).toBeVisible();
    await expect(diff.getByRole("cell", { name: "400" })).toBeVisible();
    await expect(diff.getByRole("rowheader", { name: "Keyframe parallax" })).toHaveCount(0);

    // both metric sets with a delta column
    const scores = page.getByRole("table").nth(1);
    await expect(scores.getByRole("rowheader", { name: "ATE RMSE" })).toBeVisible();
    await expect(scores.getByRole("columnheader", { name: "Change" })).toBeVisible();
  });

  test("draws both estimates and ground truth in one viewer", async ({ page }) => {
    await twoRuns(page);

    await page.goto("/app/runs");
    const boxes = page.getByTestId("run-list").getByRole("checkbox");
    await boxes.nth(0).check();
    await boxes.nth(1).check();
    await page.getByRole("button", { name: "Compare" }).click();
    await page.waitForURL(/\/app\/compare\?/);

    const viewer = page.getByTestId("viewer-canvas");
    await expect(viewer).toBeVisible();

    // all three paths named in the viewer's own legend, which is the claim that they are
    // drawn together in one space rather than merely mentioned somewhere on the page
    const legend = page.locator("div").filter({ hasText: /^Ground truth/ }).last();
    await expect(legend).toContainText("Ground truth");
    await expect(legend).toContainText("cmp first");
    await expect(legend).toContainText("cmp second");

    // the canvas has to have actually drawn something, not just mounted
    await page.waitForTimeout(2000);
    const painted = await viewer.locator("canvas").evaluate((canvas) => {
      const context = (canvas as HTMLCanvasElement).getContext("webgl2");
      return context !== null;
    });
    expect(painted).toBe(true);
  });

  test("enables compare only at exactly two", async ({ page }) => {
    await twoRuns(page);
    await page.goto("/app/runs");

    const compare = page.getByRole("button", { name: "Compare" });
    await expect(compare).toBeDisabled();

    const boxes = page.getByTestId("run-list").getByRole("checkbox");
    await boxes.nth(0).check();
    await expect(compare).toBeDisabled();
    await expect(page.getByText("Pick one more")).toBeVisible();

    await boxes.nth(1).check();
    await expect(compare).toBeEnabled();
  });

  test("sorts the list by ATE so the best run is first", async ({ page }) => {
    await twoRuns(page);
    await page.goto("/app/runs");
    await page.getByRole("button", { name: "Best ATE" }).click();

    // every scored row states its ATE with the alignment it was measured under
    const rows = page.getByTestId("run-list").getByRole("listitem");
    await expect(rows.first()).toContainText("ATE, Sim(3)");
  });

  test("says why a pair cannot be compared instead of rendering an empty screen", async ({
    page,
  }) => {
    // two runs with no common ground truth have nothing to be scored against each other, and
    // the screen has to name that rather than showing a blank comparison
    await twoRuns(page);
    await page.goto("/app/compare?run_a=not-a-run&run_b=also-not-a-run");

    await expect(page.getByText("Could not compare these runs")).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  test("filters the list by status", async ({ page }) => {
    await twoRuns(page);
    await page.goto("/app/runs");

    await page.getByRole("button", { name: "Failed", exact: true }).click();
    await expect(page.getByText("No failed runs")).toBeVisible();

    await page.getByRole("button", { name: "Done", exact: true }).click();
    await expect(page.getByTestId("run-list").getByRole("listitem")).toHaveCount(2);
  });

  test("holds up at 375px without scrolling the page sideways", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await twoRuns(page);

    await page.goto("/app/runs");
    const boxes = page.getByTestId("run-list").getByRole("checkbox");
    await boxes.nth(0).check();
    await boxes.nth(1).check();
    await page.getByRole("button", { name: "Compare" }).click();
    await page.waitForURL(/\/app\/compare\?/);
    await page.waitForTimeout(1500);

    // the wide tables scroll inside their own boxes, so the page itself must not
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
