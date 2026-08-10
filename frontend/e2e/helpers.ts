import type { Page } from "@playwright/test";

export const SEQUENCE_PATH = process.env.E2E_SEQUENCE_PATH ?? "";
/** A real directory with no sequence in it, for the "missing file" error path. */
export const EMPTY_DIR = process.env.E2E_EMPTY_DIR ?? "";

export function uniqueEmail(): string {
  const suffix = Math.random().toString(36).slice(2, 10);
  return `e2e-${Date.now()}-${suffix}@driftline.dev`;
}

export const PASSWORD = "testpassword123";

/** Registers a fresh account and lands on the datasets page. */
export async function registerAndSignIn(page: Page, email = uniqueEmail()): Promise<string> {
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/app/datasets");
  return email;
}

/** Hides the Next dev indicator so it never leaks into a screenshot. */
export async function hideDevIndicator(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const style = document.createElement("style");
    style.textContent = "nextjs-portal { display: none !important; }";
    document.documentElement.appendChild(style);
  });
}
