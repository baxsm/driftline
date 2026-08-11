import { test } from "@playwright/test";
import {
  EMPTY_DIR,
  RUN_SEQUENCE_PATH,
  SCORABLE_SEQUENCE_PATH,
  SEQUENCE_PATH,
  hideDevIndicator,
  registerAndSignIn,
  registerSequence,
} from "./helpers";

const DIR = "e2e/screenshots";
/** 3D and toasts animate in, so captures wait for them to settle rather than catch a frame. */
const SETTLE_MS = 600;

test.beforeEach(async ({ page }) => {
  await hideDevIndicator(page);
});

// One case that walks every screen in order, so it needs far longer than a normal test: it
// registers sequences, waits for real runs to finish, and settles between captures. The
// per-test default would fail it on length rather than on anything being wrong.
test("capture every meaningful state", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/login");
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/01-login.png`, fullPage: true });

  await page.goto("/register");
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/02-register.png`, fullPage: true });

  await page.getByLabel("Email").fill("not-an-email");
  await page.getByLabel("Password").fill("short");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/03-register-error.png`, fullPage: true });

  await registerAndSignIn(page);
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/04-datasets-empty.png`, fullPage: true });

  await page.getByRole("button", { name: "Register sequence" }).click();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/05-register-dialog.png`, fullPage: true });

  if (EMPTY_DIR) {
    await page.getByLabel("Path").fill(EMPTY_DIR);
    await page.getByRole("button", { name: "Register", exact: true }).click();
    await page.waitForTimeout(SETTLE_MS);
    await page.screenshot({ path: `${DIR}/06-dialog-error.png`, fullPage: true });
    await page.keyboard.press("Escape");
  }

  await page.goto("/app/runs");
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/07-runs-empty.png`, fullPage: true });

  await page.goto("/app/compare");
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/08-compare-not-built.png`, fullPage: true });

  if (RUN_SEQUENCE_PATH) {
    await registerSequence(page, RUN_SEQUENCE_PATH, "shot sequence");
    await page.getByRole("button", { name: "New run" }).click();
    await page.waitForTimeout(SETTLE_MS);
    await page.screenshot({ path: `${DIR}/15-run-config.png`, fullPage: true });

    // the mode choice is the phase 4 control, and the dialog is the one place the two
    // estimators are described next to each other
    await page.getByLabel(/visual inertial/i).click();
    await page.waitForTimeout(SETTLE_MS);
    await page.screenshot({ path: `${DIR}/15b-run-config-inertial.png`, fullPage: true });

    await page.setViewportSize({ width: 375, height: 812 });
    await page.waitForTimeout(SETTLE_MS);
    await page.screenshot({ path: `${DIR}/15c-run-config-375.png`, fullPage: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForTimeout(SETTLE_MS);
    await page.getByLabel(/visual only/i).click();

    await page.getByLabel("Max features").fill("5");
    await page.getByRole("button", { name: "Queue run" }).click();
    await page.waitForTimeout(SETTLE_MS);
    await page.screenshot({ path: `${DIR}/16-run-config-error.png`, fullPage: true });
    await page.getByLabel("Max features").fill("300");

    await page.getByLabel("Label").fill("shot run");
    await page.getByRole("button", { name: "Queue run" }).click();
    await page
      .getByRole("listitem")
      .filter({ hasText: "shot run" })
      .getByText("Done")
      .waitFor({ timeout: 60_000 });
    await page.waitForTimeout(SETTLE_MS);
    await page.screenshot({ path: `${DIR}/17-runs-populated.png`, fullPage: true });

    await page.getByRole("link", { name: "shot run" }).click();
    await page.waitForURL(/\/app\/runs\/[0-9a-f-]+$/);
    // the 3D path and the first frame both have to finish drawing
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${DIR}/18-run-detail.png`, fullPage: true });

    await page.setViewportSize({ width: 375, height: 812 });
    await page.waitForTimeout(SETTLE_MS);
    await page.screenshot({ path: `${DIR}/19-run-detail-375.png`, fullPage: true });
    await page.setViewportSize({ width: 1440, height: 900 });
  }

  // a scored run: the metrics panel, the truth overlay and the error plots only exist when
  // the sequence carries ground truth, so they need their own sequence to capture
  if (SCORABLE_SEQUENCE_PATH) {
    await registerSequence(page, SCORABLE_SEQUENCE_PATH, "shot scorable");
    await page.getByRole("button", { name: "New run" }).click();
    await page.getByLabel("Label").fill("shot scored");
    await page.getByRole("button", { name: "Queue run" }).click();
    await page
      .getByRole("listitem")
      .filter({ hasText: "shot scored" })
      .getByText("Done")
      .waitFor({ timeout: 60_000 });

    await page.getByRole("link", { name: "shot scored" }).click();
    await page.waitForURL(/\/app\/runs\/[0-9a-f-]+$/);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${DIR}/20-run-scored.png`, fullPage: true });

    // the selection is shared by the plots, the slider and the 3D marker
    await page.getByRole("button", { name: "Jump to worst pose" }).click();
    await page.waitForTimeout(SETTLE_MS);
    await page.screenshot({ path: `${DIR}/21-run-scored-worst.png`, fullPage: true });

    await page.setViewportSize({ width: 375, height: 812 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${DIR}/22-run-scored-375.png`, fullPage: true });
    await page.setViewportSize({ width: 1440, height: 900 });
  }

  if (!SEQUENCE_PATH) return;

  await page.goto("/app/datasets");
  await page.getByRole("button", { name: "Register sequence" }).click();
  await page.getByLabel("Path").fill(SEQUENCE_PATH);
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/09-datasets-populated.png`, fullPage: true });

  // the toast sits bottom right over the list, so it is dismissed before navigating
  await page.locator("[data-sonner-toast]").first().hover();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);

  await page
    .getByTestId("dataset-list")
    .getByRole("listitem")
    .first()
    .getByRole("link")
    .first()
    .click();
  await page.waitForURL(/\/app\/datasets\/[0-9a-f-]+$/);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${DIR}/10-dataset-detail.png`, fullPage: true });

  await page.setViewportSize({ width: 375, height: 812 });
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/11-detail-375.png`, fullPage: true });

  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/12-mobile-nav.png`, fullPage: true });

  await page.keyboard.press("Escape");
  await page.goto("/app/datasets");
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/13-datasets-375.png`, fullPage: true });

  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto("/login");
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({ path: `${DIR}/14-login-768.png`, fullPage: true });
});
