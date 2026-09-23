import { expect, test } from "@playwright/test";

test("create, publish, activate, and roll back an agent", async ({ page }) => {
	await page.goto("/");
	await page.getByLabel("Email").fill(process.env.VF_E2E_EMAIL ?? "");
	await page.getByLabel("Password").fill(process.env.VF_E2E_PASSWORD ?? "");
	await page.getByRole("button", { name: "Sign in" }).click();
	const editor = page.getByRole("region", { name: "Agent configurations" });
	await expect(editor).toBeVisible();
	await editor.getByLabel("Name").fill("E2E receptionist");
	await editor.getByLabel("Instructions").fill("Welcome callers");
	await editor.getByRole("button", { name: "Create" }).click();
	await expect(editor.getByText("Draft revision 1")).toBeVisible();
	await editor.getByRole("button", { name: "Publish draft" }).click();
	await expect(editor.getByText("Published v1.")).toBeVisible();
	await editor
		.getByLabel("Configuration JSON")
		.fill(JSON.stringify({ schema_version: 1, instructions: "Welcome back" }));
	await editor.getByRole("button", { name: "Save draft" }).click();
	await expect(editor.getByText("Draft revision 3")).toBeVisible();
	await editor.getByRole("button", { name: "Publish draft" }).click();
	await expect(editor.getByText("Published v2.")).toBeVisible();
	await editor
		.getByRole("listitem")
		.filter({ hasText: "v2" })
		.getByRole("button", { name: "Activate locally" })
		.click();
	await expect(editor.getByText("Local active version: 2")).toBeVisible();
	await editor
		.getByRole("listitem")
		.filter({ hasText: "v1" })
		.getByRole("button", { name: "Activate locally" })
		.click();
	await expect(editor.getByText("Local active version: 1")).toBeVisible();
});
