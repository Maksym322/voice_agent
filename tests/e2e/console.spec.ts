import { expect, test } from "@playwright/test";

test("console navigation uses real empty states and saves a personal board view", async ({
	page,
}) => {
	await page.goto("/");
	await page.getByLabel("Email").fill(process.env.VF_E2E_EMAIL ?? "");
	await page.getByLabel("Password").fill(process.env.VF_E2E_PASSWORD ?? "");
	await page.getByRole("button", { name: "Sign in" }).click();
	await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
	await expect(page.getByText("Voice worker: unverified")).toBeVisible();
	await page.getByRole("button", { name: "Agents", exact: true }).click();
	await expect(page.getByRole("button", { name: "Call test phone" })).toBeDisabled();
	await page.getByRole("button", { name: "Live board", exact: true }).click();
	await expect(
		page.getByRole("region", { name: "pending sessions" }),
	).toContainText("No sessions");
	await page.getByRole("button", { name: "History" }).click();
	await expect(page.getByText("No matching sessions.")).toBeVisible();
	await page.getByRole("button", { name: "Logs" }).click();
	await expect(
		page.getByText("No diagnostics match the filters."),
	).toBeVisible();
	await page.getByRole("button", { name: "Settings" }).click();
	await page.getByRole("checkbox", { name: "Channel" }).check();
	await page.getByRole("button", { name: "Save my view" }).click();
	await expect(page.getByText("Your board view was saved.")).toBeVisible();
	await page.reload();
	await page.getByRole("button", { name: "Settings" }).click();
	await expect(page.getByRole("checkbox", { name: "Channel" })).toBeChecked();
});
