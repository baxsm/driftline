import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.e2e\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  timeout: 45_000,
  use: {
    baseURL: BASE_URL,
    trace: "off",
    screenshot: "off",
    // the viewer needs real WebGL, so these run headed-equivalent with a GPU-backed context
    launchOptions: { args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl"] },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
});
