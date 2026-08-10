import { expect, test } from "@playwright/test";
import { PASSWORD, hideDevIndicator, registerAndSignIn, uniqueEmail } from "./helpers";

test.beforeEach(async ({ page }) => {
  await hideDevIndicator(page);
});

test("register lands on datasets", async ({ page }) => {
  await registerAndSignIn(page);
  await expect(page.getByRole("heading", { name: "Datasets" })).toBeVisible();
});

test("a new account sees the empty state with a dataset url", async ({ page }) => {
  await registerAndSignIn(page);
  await expect(page.getByText("No sequences registered")).toBeVisible();
  await expect(page.getByText(/dataset-room1_512_16\.tar/)).toBeVisible();
});

test("signing out returns to login and blocks the app", async ({ page }) => {
  await registerAndSignIn(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("**/login");

  await page.goto("/app/datasets");
  await page.waitForURL("**/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("sign in with the wrong password shows an error and stays put", async ({ page }) => {
  const email = await registerAndSignIn(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("**/login");

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("wrongpassword1");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.locator("p[role=\"alert\"]")).toContainText("do not match");
  await expect(page).toHaveURL(/\/login/);
});

test("sign in with the right password reaches the app", async ({ page }) => {
  const email = await registerAndSignIn(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("**/login");

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/app/datasets");
});

test("registering a taken email names the field", async ({ page }) => {
  const email = await registerAndSignIn(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("**/login");

  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.locator("p[role=\"alert\"]")).toContainText("already registered");
});

test("a short password is rejected by the server rules, not the browser", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill("short");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.locator("p[role=\"alert\"]")).toContainText("at least 8 characters");
});

test("a signed in user is pushed off the login page", async ({ page }) => {
  await registerAndSignIn(page);
  await page.goto("/login");
  await page.waitForURL("**/app/datasets");
});
