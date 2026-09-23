import { expect, test } from "@playwright/test";

test("anonymous access, sign-in, sign-out, and old-cookie replay", async ({ page, context }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByLabel("Dashboard")).not.toBeVisible();

  await page.getByLabel("Email").fill(process.env.VF_E2E_EMAIL ?? "");
  await page.getByLabel("Password").fill("incorrect");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid credentials");

  await page.getByLabel("Password").fill(process.env.VF_E2E_PASSWORD ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByLabel("Dashboard")).toContainText(process.env.VF_E2E_EMAIL ?? "");
  const oldCookie = (await context.cookies()).find((cookie) => cookie.name === "vf_session");
  expect(oldCookie).toBeDefined();
  if (!oldCookie) throw new Error("Session cookie missing after sign-in");

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await context.addCookies([oldCookie]);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
