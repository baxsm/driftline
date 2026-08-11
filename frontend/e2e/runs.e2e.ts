import { expect, test } from "@playwright/test";
import {
  queueRunAndWait,
  registerAndSignIn,
  registerSequence,
  RUN_SEQUENCE_PATH,
} from "./helpers";

/**
 * These drive a real run: the browser queues it, the worker executes the estimator over real
 * image files, and the page follows it to completion. Nothing here is stubbed, so a passing
 * test means the whole chain works, not just the components.
 */
test.describe("runs", () => {
  test.skip(!RUN_SEQUENCE_PATH, "set E2E_RUN_SEQUENCE_PATH to a short rendered sequence");

  test.beforeEach(async ({ page }) => {
    await registerAndSignIn(page);
  });

  test("says the estimator has no runs rather than showing an empty table", async ({ page }) => {
    await page.goto("/app/runs");
    await expect(page.getByText("No runs yet")).toBeVisible();
    await expect(page.getByRole("link", { name: "Go to sequences" })).toBeVisible();
  });

  test("queues a run and follows it to done", async ({ page }) => {
    await registerSequence(page, RUN_SEQUENCE_PATH, "e2e line");
    await queueRunAndWait(page, "e2e baseline");

    // a finished run is the normal case and carries no badge, so what marks it as finished is
    // the score cell settling and the frame count reaching the total
    const row = page.getByRole("listitem").filter({ hasText: "e2e baseline" });
    await expect(row.getByText("Done")).toHaveCount(0);
    await expect(row.getByText(/ATE|not scored/)).toBeVisible();
    await expect(row).toContainText("of");
  });

  test("draws the estimated path and the tracked features", async ({ page }) => {
    await registerSequence(page, RUN_SEQUENCE_PATH, "e2e viewer");
    await queueRunAndWait(page, "e2e viewer run");

    await page.getByRole("link", { name: "e2e viewer run" }).click();
    await page.waitForURL("**/app/runs/**");

    await expect(page.getByText("Estimated path")).toBeVisible();
    await expect(page.getByTestId("viewer-canvas")).toBeVisible();
    // the viewer must say which frame the distances are in. A scorable sequence aligns onto
    // truth and is in metres; without truth a mono estimate has no absolute scale. Either is
    // honest, silently implying metres is not.
    await expect(
      page.getByText(/no absolute scale|Aligned onto ground truth/),
    ).toBeVisible();

    const canvas = page.getByTestId("tracking-canvas");
    await canvas.scrollIntoViewIfNeeded();
    await expect(canvas).toBeVisible();
    await expect(page.getByText(/features tracked into this frame/)).toBeVisible();
  });

  test("the scrubber moves to another frame", async ({ page }) => {
    await registerSequence(page, RUN_SEQUENCE_PATH, "e2e scrub");
    await queueRunAndWait(page, "e2e scrub run");

    await page.getByRole("link", { name: "e2e scrub run" }).click();
    await page.waitForURL("**/app/runs/**");

    const scrubber = page.getByRole("slider", { name: "Frame" });
    await scrubber.scrollIntoViewIfNeeded();
    await expect(scrubber).toHaveValue("0");

    await scrubber.fill("8");
    await expect(scrubber).toHaveValue("8");
    await expect(page.getByText("8 /", { exact: false })).toBeVisible();
  });

  test("the tracking canvas draws real pixels, not a blank rectangle", async ({ page }) => {
    await registerSequence(page, RUN_SEQUENCE_PATH, "e2e pixels");
    await queueRunAndWait(page, "e2e pixels run");

    await page.getByRole("link", { name: "e2e pixels run" }).click();
    await page.waitForURL("**/app/runs/**");
    await page.getByTestId("tracking-canvas").scrollIntoViewIfNeeded();
    await page.waitForTimeout(1500);

    // a canvas that failed to load its frame still renders as an element, so the only honest
    // check is reading the pixels back and confirming more than one colour is present
    const distinctColours = await page.evaluate(() => {
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="tracking-canvas"]',
      );
      const context = canvas?.getContext("2d");
      if (!canvas || !context) return 0;
      const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
      const seen = new Set<string>();
      for (let i = 0; i < data.length; i += 4 * 97) {
        seen.add(`${data[i]},${data[i + 1]},${data[i + 2]}`);
      }
      return seen.size;
    });
    expect(distinctColours).toBeGreaterThan(3);
  });

  test("rejects a config value the server would reject, without a round trip", async ({ page }) => {
    await registerSequence(page, RUN_SEQUENCE_PATH, "e2e config");

    await page.getByRole("button", { name: "New run" }).click();
    await page.getByLabel("Max features").fill("5");
    await page.getByRole("button", { name: "Queue run" }).click();

    await expect(page.getByRole("alert")).toContainText("between 50 and 2000");
    await expect(page.getByRole("button", { name: "Queue run" })).toBeVisible();
  });

  test("a deleted run leaves the list", async ({ page }) => {
    await registerSequence(page, RUN_SEQUENCE_PATH, "e2e delete");
    await queueRunAndWait(page, "e2e delete run");

    await page.goto("/app/runs");
    const row = page.getByRole("listitem").filter({ hasText: "e2e delete run" });
    await row.getByRole("button", { name: "Delete" }).click();

    await expect(page.getByText("e2e delete run")).toBeHidden();
  });

  test("runs and their controls fit a phone", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await registerSequence(page, RUN_SEQUENCE_PATH, "e2e mobile");
    await queueRunAndWait(page, "e2e mobile run");

    await page.getByRole("link", { name: "e2e mobile run" }).click();
    await page.waitForURL("**/app/runs/**");

    const scrubber = page.getByRole("slider", { name: "Frame" });
    await scrubber.scrollIntoViewIfNeeded();
    await expect(scrubber).toBeVisible();

    // nothing may push the page wider than the phone, which is what turns a layout into a
    // horizontal scroll
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("shows the estimator log on demand", async ({ page }) => {
    // the failure banner states the conclusion; the log is the working behind it, and it is
    // collapsed by default because it is a diagnostic rather than part of reading a good run
    await registerSequence(page, RUN_SEQUENCE_PATH, "e2e log");
    await queueRunAndWait(page, "e2e log run");

    await page.getByRole("link", { name: "e2e log run" }).click();
    await page.waitForURL("**/app/runs/**");

    const toggle = page.getByRole("button", { name: "Show log" });
    await toggle.scrollIntoViewIfNeeded();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");

    await toggle.click();
    await expect(page.getByRole("button", { name: "Hide log" })).toBeVisible();
    await expect(page.getByText(/camera model/)).toBeVisible();
  });
});
