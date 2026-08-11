import { defineConfig, devices } from "@playwright/test";

/**
 * The readme figures, run on their own with `npm run readme:shots`.
 *
 * Separate from `playwright.config.ts` because these sign into the staged demo account and
 * the e2e suite registers and unregisters sequences as it goes. Run together, the suite takes
 * that profile apart underneath the captures: unregistering a sequence cascades to every run
 * scored against it, so the figures end up drawn from an account with nothing in it.
 */
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.capture\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  timeout: 180_000,
  use: {
    baseURL: BASE_URL,
    trace: "off",
    screenshot: "off",
    // the viewer needs real WebGL, so these run with a GPU-backed context
    launchOptions: { args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl"] },
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
});
