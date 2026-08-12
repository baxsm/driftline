import { expect, test } from "@playwright/test";
import {
  queueRunAndWait,
  registerAndSignIn,
  registerSequence,
  SCORABLE_SEQUENCE_PATH,
  UNSCORABLE_SEQUENCE_PATH,
} from "./helpers";

/**
 * Scoring, driven all the way through a real browser.
 *
 * The run is queued from the page, the worker executes the estimator and scores the result,
 * and the numbers here are read back off the rendered panel. Nothing is stubbed, so these
 * failing means the chain is broken rather than a component being mis-wired.
 */
test.describe("metrics", () => {
  test.skip(
    !SCORABLE_SEQUENCE_PATH,
    "set E2E_SCORABLE_SEQUENCE_PATH to a rendered sequence with ground truth",
  );

  test.beforeEach(async ({ page }) => {
    await registerAndSignIn(page);
  });

  async function openScoredRun(page: import("@playwright/test").Page, name: string) {
    await registerSequence(page, SCORABLE_SEQUENCE_PATH, name);
    await queueRunAndWait(page, `${name} run`);
    await page.getByRole("link", { name: `${name} run` }).click();
    await page.waitForURL("**/app/runs/**");
  }

  test("shows the scores with the alignment mode next to them", async ({ page }) => {
    await openScoredRun(page, "e2e scored");

    await expect(page.getByText("Accuracy")).toBeVisible();
    // a monocular estimate has no scale of its own, so it must be Sim(3) aligned
    await expect(page.getByText("Sim(3) aligned")).toBeVisible();
    await expect(page.getByText("ATE RMSE")).toBeVisible();
    await expect(page.getByText("Poses matched")).toBeVisible();
    // the caveat travels with the number, because a Sim(3) ATE is not comparable to an SE(3) one
    await expect(page.getByText(/cannot be compared against an SE\(3\)/)).toBeVisible();
  });

  test("overlays the aligned estimate on ground truth", async ({ page }) => {
    await openScoredRun(page, "e2e overlay");

    await expect(page.getByText("Estimate against ground truth")).toBeVisible();
    await expect(page.getByText(/distances are in metres/)).toBeVisible();
    await expect(page.getByTestId("viewer-canvas")).toBeVisible();
    // both paths are drawn, and the estimate says what its colours mean
    await expect(page.getByText("Ground truth", { exact: true })).toBeVisible();
    await expect(page.getByText(/Estimate, 0 to .* off/)).toBeVisible();
  });

  test("moves the plots, the slider and the 3D marker together", async ({ page }) => {
    await openScoredRun(page, "e2e linked");

    const slider = page.getByRole("slider", { name: "Pose" });
    await slider.scrollIntoViewIfNeeded();
    await expect(slider).toHaveValue("0");

    await page.getByRole("button", { name: "Jump to worst pose" }).click();

    // the selection is shared, so the readout follows the jump
    const moved = await slider.inputValue();
    expect(Number(moved)).toBeGreaterThan(0);
    await expect(slider).toHaveAttribute("aria-valuetext", /position error/);
  });

  test("the slider moves with the keyboard", async ({ page }) => {
    /**
     * jsdom does not implement the range input's own key handling, so the component test
     * cannot cover this. A real browser does, which is the point of checking it here.
     */
    await openScoredRun(page, "e2e keys");

    const slider = page.getByRole("slider", { name: "Pose" });
    await slider.scrollIntoViewIfNeeded();
    await slider.focus();
    await page.keyboard.press("ArrowRight");

    await expect(slider).toHaveValue("1");
  });

  test("says a sequence without ground truth cannot be scored", async ({ page }) => {
    test.skip(
      !UNSCORABLE_SEQUENCE_PATH,
      "set E2E_UNSCORABLE_SEQUENCE_PATH to a sequence with no ground truth",
    );
    await registerSequence(page, UNSCORABLE_SEQUENCE_PATH, "e2e unscored");
    await queueRunAndWait(page, "e2e unscored run");
    await page.getByRole("link", { name: "e2e unscored run" }).click();
    await page.waitForURL("**/app/runs/**");

    // the honest empty state: not zeros, which would read as a perfect estimate
    await expect(page.getByText(/no ground truth, so the estimate cannot be scored/)).toBeVisible();
    await expect(page.getByText("ATE RMSE")).toHaveCount(0);
  });

  test("holds up at 375px without overflowing", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await openScoredRun(page, "e2e mobile");

    await expect(page.getByText("Sim(3) aligned")).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);

    // the plots stack rather than being squeezed side by side on a phone
    const slider = page.getByRole("slider", { name: "Pose" });
    await slider.scrollIntoViewIfNeeded();
    await expect(slider).toBeVisible();
  });

  test("exports a TUM file for both the estimate and the truth", async ({ page }) => {
    await openScoredRun(page, "e2e export");
    const runUrl = page.url();
    const runId = runUrl.split("/").pop();

    // through the app's own origin, the same path the browser uses, so this exercises the
    // proxy rather than a route the running app never takes
    for (const kind of ["estimate", "truth"]) {
      const response = await page.request.get(`/api/runs/${runId}/export?kind=${kind}`);
      expect(response.status()).toBe(200);
      const body = await response.text();
      const rows = body.split("\n").filter((line) => line && !line.startsWith("#"));
      expect(rows.length).toBeGreaterThan(0);
      // TUM is timestamp, position, then a quaternion: eight columns
      expect(rows[0].split(" ")).toHaveLength(8);
    }
  });
});
