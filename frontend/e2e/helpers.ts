import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import type { Page } from "@playwright/test";

/**
 * Sequences live in the repo's own gitignored `data/` folder, so the suite finds them without
 * any environment plumbing. The env vars still win where they are set, which is what a machine
 * keeping its sequences somewhere else needs.
 *
 * The backend resolves these paths, and it runs on this machine, so an absolute path is what it
 * needs rather than one relative to the test process.
 */
const DATA_ROOT = resolve(__dirname, "..", "..", "data");

function sequence(override: string | undefined, name: string): string {
  if (override) return override;
  const path = join(DATA_ROOT, name);
  return existsSync(path) ? path : "";
}

export const SEQUENCE_PATH = sequence(process.env.E2E_SEQUENCE_PATH, "dataset-room1_512_16");
/** A real directory with no sequence in it, for the "missing file" error path. */
export const EMPTY_DIR = sequence(process.env.E2E_EMPTY_DIR, "empty-dir");
/** A short rendered sequence, so a whole run finishes inside a test. */
export const RUN_SEQUENCE_PATH = sequence(process.env.E2E_RUN_SEQUENCE_PATH, "synthetic-short");
/** A rendered sequence carrying ground truth, so a run over it can be scored. */
export const SCORABLE_SEQUENCE_PATH = sequence(
  process.env.E2E_SCORABLE_SEQUENCE_PATH,
  "synthetic-scorable",
);
/**
 * A rendered sequence with no ground truth, for the unscorable path. It has to be a sequence
 * that genuinely has none: a scorable one gets scored, and the test would then be asserting
 * the absence of a panel that is correctly present.
 */
export const UNSCORABLE_SEQUENCE_PATH = sequence(
  process.env.E2E_UNSCORABLE_SEQUENCE_PATH,
  "synthetic-line",
);

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

/** Registers a sequence from the datasets page and opens it. */
export async function registerSequence(page: Page, path: string, name: string): Promise<void> {
  await page.goto("/app/datasets");
  await page.getByRole("button", { name: "Register sequence" }).click();
  await page.getByLabel("Path").fill(path);
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Register" }).click();
  await page.getByRole("link", { name }).click();
  await page.waitForURL("**/app/datasets/**");
}

/** Queues a run from the sequence page and waits for the worker to finish it. */
export async function queueRunAndWait(page: Page, label: string): Promise<void> {
  await page.getByRole("button", { name: "New run" }).click();
  await page.getByLabel("Label").fill(label);
  await page.getByRole("button", { name: "Queue run" }).click();
  // the list polls while anything is in flight, so the terminal status arrives on its own
  await page.getByRole("listitem").filter({ hasText: label }).getByText("Done").waitFor({
    timeout: 60_000,
  });
}

/** Hides the Next dev indicator so it never leaks into a screenshot. */
export async function hideDevIndicator(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const style = document.createElement("style");
    style.textContent = "nextjs-portal { display: none !important; }";
    document.documentElement.appendChild(style);
  });
}
