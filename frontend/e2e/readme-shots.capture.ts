import { type Page, expect, test } from "@playwright/test";
import { hideDevIndicator } from "./helpers";

/**
 * Captures the README images from a profile staged with real room1 runs, rather than from the
 * synthetic sequences the rest of the suite builds. It asserts on the real numbers before it
 * captures, so a screenshot can never show a screen that failed to load its data.
 *
 * Staged by scripts/stage-readme-demo.py and run on its own with `npm run readme:shots`.
 *
 * Deliberately not a `.e2e.ts` file. The suite registers and unregisters sequences as it
 * goes, and unregistering cascades to every run scored against the sequence, so running
 * these alongside it draws the figures from an account the suite has just emptied.
 *
 * Nothing here captures with `fullPage`. A full page capture resizes the page to its whole
 * scroll height, and the trajectory canvas does not refit to that: the path renders against
 * the size the camera was fitted for and ends up in a corner of a much larger image, with the
 * rest of the page left black. Viewport and element captures both render it correctly.
 */

const DIR = "e2e/readme";
const EMAIL = process.env.README_EMAIL ?? "demo@driftline.dev";
const PASSWORD = process.env.README_PASSWORD ?? "driftline-demo-2026";
/** Panels and toasts fade in, so captures wait for them to settle rather than catch a frame. */
const SETTLE_MS = 700;

test.use({ deviceScaleFactor: 2 });

async function signIn(page: Page): Promise<void> {
  await hideDevIndicator(page);
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/app/datasets");
}

/** The trajectory canvas. A run screen also carries the camera frame, which comes second. */
function viewer(page: Page) {
  return page.locator("canvas").first();
}

/**
 * Captures the viewer as a viewport shot with the canvas filling the frame.
 *
 * The canvas is captured through the viewport rather than as an element. An element capture
 * grows the viewport to fit, and the canvas follows that growth and redraws against a size the
 * camera was not fitted for, which puts the path in a corner. Scrolling the panel to the top
 * of an ordinary viewport gets the same framing without resizing anything.
 */
async function captureViewer(page: Page, path: string, panelTitle: string): Promise<void> {
  // scrolled by hand rather than with scrollIntoViewIfNeeded, which does nothing once the
  // title is technically on screen and leaves the canvas hanging below the fold
  const title = page.getByText(panelTitle).first();
  await title.evaluate((el) => el.scrollIntoView({ block: "start", behavior: "instant" }));
  await page.waitForTimeout(SETTLE_MS);
  await page.getByRole("button", { name: "Reset view" }).first().click();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path });
}

/**
 * Waits for the drawn path, brings the viewer into frame, then refits it.
 *
 * The reset runs after the scroll so the fit is measured once the panel has stopped moving,
 * and the wait on the legend is what proves truth actually arrived: the overlay is fetched
 * separately from the estimate, so a fixed timeout can capture a viewer holding one line.
 */
async function settleViewer(page: Page, panelTitle: string): Promise<void> {
  await expect(page.getByText("Ground truth").first()).toBeVisible();
  await page.getByText(panelTitle).first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(SETTLE_MS);
  await page.getByRole("button", { name: "Reset view" }).first().click();
  await page.waitForTimeout(SETTLE_MS);
}

test("capture the run screens", async ({ page }) => {
  test.setTimeout(180_000);
  await signIn(page);

  // the runs list is the "which config won" screen, so it is captured sorted by accuracy
  await page.goto("/app/runs");
  await page.getByRole("button", { name: "Best ATE" }).click();
  await expect(page.getByText("49.5 cm")).toBeVisible();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/runs.png` });

  // the inertial run: the best result, and the only one that measured its own scale
  await page.getByRole("link", { name: "visual inertial, metric scale" }).click();
  await page.waitForURL(/\/app\/runs\/[0-9a-f-]+$/);
  await expect(page.getByText("SE(3) aligned")).toBeVisible();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/metrics-inertial.png` });

  await settleViewer(page, "Estimate against ground truth");
  await page.screenshot({ path: `${DIR}/run-inertial.png` });
  await captureViewer(page, `${DIR}/viewer-inertial.png`, "Estimate against ground truth");

  // the monocular run, whose scale had to be fitted onto truth. Captured for the contrast:
  // same sequence, same estimator, and a scale figure the inertial run does not need.
  await page.goto("/app/runs");
  await page.getByRole("link", { name: "baseline, 600 features" }).click();
  await page.waitForURL(/\/app\/runs\/[0-9a-f-]+$/);
  await expect(page.getByText("Sim(3) aligned")).toBeVisible();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/metrics-mono.png` });

  await settleViewer(page, "Estimate against ground truth");
  await captureViewer(page, `${DIR}/viewer-mono.png`, "Estimate against ground truth");

  /*
   * The error plots and the real camera frame with its tracked points, which is the part that
   * shows why a run drifted rather than by how much.
   *
   * Captured on the monocular run rather than the inertial one. This run drifts worst near the
   * end, at pose 2,446 of 2,773, so jumping to the worst pose moves the whole selection and the
   * frame on screen is the one it was furthest from truth on. The inertial run's largest error
   * is its first pose, where the estimate is still settling, so the same jump would sit at pose
   * one and read as a control that does nothing.
   */
  await page.getByRole("button", { name: "Jump to worst pose" }).click();
  await expect(page.getByText(/Pose 2,4\d\d of 2,773/)).toBeVisible();
  await page
    .getByText("Error over the run", { exact: true })
    .first()
    .evaluate((el) => el.scrollIntoView({ block: "start", behavior: "instant" }));
  await page.waitForTimeout(SETTLE_MS * 2);
  await page.screenshot({ path: `${DIR}/inspector.png` });
});

test("capture the sequence and config screens", async ({ page }) => {
  test.setTimeout(180_000);
  await signIn(page);
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/datasets.png` });

  await page.getByRole("link", { name: "TUM VI room1" }).click();
  await page.waitForURL(/\/app\/datasets\/[0-9a-f-]+$/);
  await expect(page.getByText("2,821", { exact: true }).first()).toBeVisible();
  await settleViewer(page, "Ground truth path");
  await page.screenshot({ path: `${DIR}/dataset-detail.png` });
  await captureViewer(page, `${DIR}/viewer-truth.png`, "Ground truth path");

  await page.getByRole("button", { name: "New run" }).click();
  await expect(page.getByLabel("Max features")).toBeVisible();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/run-config.png` });
});

test("capture the compare screen", async ({ page }) => {
  test.setTimeout(180_000);
  await signIn(page);

  await page.goto("/app/runs");
  const boxes = page.getByTestId("run-list").getByRole("checkbox");
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/runs-two-picked.png` });

  await page.getByRole("button", { name: "Compare" }).click();
  await page.waitForURL(/\/app\/compare\?/);
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/compare.png` });

  await settleViewer(page, "Both paths");
  await captureViewer(page, `${DIR}/viewer-compare.png`, "Both paths");
});
