import { expect, test } from "@playwright/test";
import { EMPTY_DIR, SEQUENCE_PATH, hideDevIndicator, registerAndSignIn } from "./helpers";

test.beforeEach(async ({ page }) => {
  await hideDevIndicator(page);
});

test("a path that does not exist says so", async ({ page }) => {
  await registerAndSignIn(page);
  await page.getByRole("button", { name: "Register sequence" }).click();
  await page.getByLabel("Path").fill("F:/definitely-not-a-sequence");
  await page.getByRole("button", { name: "Register", exact: true }).click();

  await expect(page.locator('p[role="alert"]')).toContainText("not a directory");
});

test("a real folder without the sequence files names the missing file", async ({ page }) => {
  test.skip(!EMPTY_DIR, "E2E_EMPTY_DIR is not set");
  await registerAndSignIn(page);
  await page.getByRole("button", { name: "Register sequence" }).click();
  await page.getByLabel("Path").fill(EMPTY_DIR);
  await page.getByRole("button", { name: "Register", exact: true }).click();

  await expect(page.locator('p[role="alert"]')).toContainText("mav0/cam0/data.csv");
});

test("submitting an empty path is caught before a request", async ({ page }) => {
  await registerAndSignIn(page);
  await page.getByRole("button", { name: "Register sequence" }).click();
  await page.getByRole("button", { name: "Register", exact: true }).click();

  await expect(page.locator("p[role=\"alert\"]")).toContainText("Enter the path");
});

test.describe("with a real sequence on disk", () => {
  test.skip(!SEQUENCE_PATH, "E2E_SEQUENCE_PATH is not set");

  test("register a sequence, open it, and see the ground truth path render", async ({ page }) => {
    await registerAndSignIn(page);

    await page.getByRole("button", { name: "Register sequence" }).click();
    await page.getByLabel("Path").fill(SEQUENCE_PATH);
    await page.getByRole("button", { name: "Register", exact: true }).click();

    const row = page.getByTestId("dataset-list").getByRole("listitem").first();
    await expect(row).toBeVisible();
    await expect(row).toContainText("TUM VI");
    await expect(row).toContainText("Ground truth");
    await expect(row).toContainText("2,821 frames");

    await row.getByRole("link").first().click();

    await expect(page.getByRole("heading", { name: "Ground truth path" })).toBeVisible();
    await expect(page.getByText("pinhole-equi").first()).toBeVisible();

    // the viewer must actually put a WebGL canvas on the page, not just reserve space
    const canvas = page.locator('[data-testid="viewer-canvas"] canvas');
    await expect(canvas).toBeVisible();

    const drew = await canvas.evaluate((element) => {
      const gl = (element as HTMLCanvasElement).getContext("webgl2");
      return gl !== null && (element as HTMLCanvasElement).width > 0;
    });
    expect(drew).toBe(true);

    await expect(page.getByRole("button", { name: "Reset view" })).toBeVisible();
  });

  test("calibration is shown as readable rows, not raw json", async ({ page }) => {
    await registerAndSignIn(page);
    await page.getByRole("button", { name: "Register sequence" }).click();
    await page.getByLabel("Path").fill(SEQUENCE_PATH);
    await page.getByRole("button", { name: "Register", exact: true }).click();
    await page.getByTestId("dataset-list").getByRole("listitem").first().getByRole("link").first().click();

    await expect(page.getByRole("heading", { name: "Calibration" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "cam0" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "cam1" })).toBeVisible();
    await expect(page.getByText("190.9785")).toBeVisible();
    // the real TUM VI accelerometer random walk, which differs from the EuRoC default
    await expect(page.getByText("0.00086")).toBeVisible();
  });

  test("unregistering removes the row", async ({ page }) => {
    await registerAndSignIn(page);
    await page.getByRole("button", { name: "Register sequence" }).click();
    await page.getByLabel("Path").fill(SEQUENCE_PATH);
    await page.getByRole("button", { name: "Register", exact: true }).click();

    await expect(page.getByTestId("dataset-list").getByRole("listitem")).toHaveCount(1);
    await page.getByRole("button", { name: "Unregister" }).click();
    await expect(page.getByText("No sequences registered")).toBeVisible();
  });

  test("registering the same path twice is refused", async ({ page }) => {
    await registerAndSignIn(page);
    for (const _ of [0, 1]) {
      await page.getByRole("button", { name: "Register sequence" }).click();
      await page.getByLabel("Path").fill(SEQUENCE_PATH);
      await page.getByRole("button", { name: "Register", exact: true }).click();
    }
    await expect(page.locator("p[role=\"alert\"]")).toContainText("already registered");
  });
});
