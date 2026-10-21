import { expect, test } from "@playwright/test";

test("create, publish, activate, and roll back an agent", async ({ page }) => {
	await page.goto("/");
	await page.getByLabel("Email").fill(process.env.VF_E2E_EMAIL ?? "");
	await page.getByLabel("Password").fill(process.env.VF_E2E_PASSWORD ?? "");
	await page.getByRole("button", { name: "Sign in" }).click();
	await page.getByRole("button", { name: "Agents", exact: true }).click();
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

test("explicit voice LLM provider controls, field preservation, and viewer read-only", async ({
	page,
}) => {
	await page.goto("/");
	await page.getByLabel("Email").fill(process.env.VF_E2E_EMAIL ?? "");
	await page.getByLabel("Password").fill(process.env.VF_E2E_PASSWORD ?? "");
	await page.getByRole("button", { name: "Sign in" }).click();
	await page.getByRole("button", { name: "Agents", exact: true }).click();
	const editor = page.getByRole("region", { name: "Agent configurations" });
	await expect(editor).toBeVisible();

	// 1. Verify new-agent form starts with Google / gemini-3.5-flash-lite preset
	await expect(editor.getByLabel("LLM provider")).toHaveValue("google");
	await expect(editor.getByLabel("LLM model")).toHaveValue("gemini-3.5-flash-lite");
	await expect(
		editor.getByText("Selected LLM: Google / gemini-3.5-flash-lite"),
	).toBeVisible();

	// 2. Create agent with Google preset and verify saved draft
	await editor.getByLabel("Name").fill("Voice pilot");
	await editor.getByLabel("Instructions").fill("Pilot instructions");
	await editor.getByRole("button", { name: "Create" }).click();
	await expect(editor.getByText("Draft revision 1")).toBeVisible();
	await expect(
		editor.getByText("Draft LLM: google / gemini-3.5-flash-lite"),
	).toBeVisible();
	await expect(editor.getByText("Local active version: none")).toBeVisible();
	await expect(editor.getByText("Local active LLM: unavailable")).toBeVisible();

	// 3. Save an OpenAI configuration with unrelated fields
	const openAiConfig = {
		schema_version: 1,
		instructions: "Pilot instructions",
		locale: "uk-UA",
		timezone: "Europe/Kyiv",
		tool_allowlist: ["crm_lookup"],
		voice: {
			llm_provider: "openai",
			llm_model: "gpt-4o-mini",
		},
	};
	await editor
		.getByLabel("Configuration JSON")
		.fill(JSON.stringify(openAiConfig, null, 2));
	await editor.getByRole("button", { name: "Save draft" }).click();
	await expect(editor.getByText("Draft saved.")).toBeVisible();
	await expect(
		editor.getByText("Draft LLM: openai / gpt-4o-mini"),
	).toBeVisible();
	await expect(editor.getByLabel("LLM provider")).toHaveValue("openai");
	await expect(editor.getByLabel("LLM model")).toHaveValue("gpt-4o-mini");

	// 4. Change provider to Google via dropdown; verify preservation of unrelated fields
	await editor.getByLabel("LLM provider").selectOption("google");
	await expect(editor.getByLabel("LLM model")).toHaveValue("gemini-3.5-flash-lite");
	const updatedJson = await editor.getByLabel("Configuration JSON").inputValue();
	const parsed = JSON.parse(updatedJson);
	expect(parsed.voice.llm_provider).toBe("google");
	expect(parsed.voice.llm_model).toBe("gemini-3.5-flash-lite");
	expect(parsed.locale).toBe("uk-UA");
	expect(parsed.timezone).toBe("Europe/Kyiv");
	expect(parsed.tool_allowlist).toEqual(["crm_lookup"]);

	// 5. Malformed JSON produces a visible error and prevents destructive save
	await editor.getByLabel("Configuration JSON").fill("{ malformed json");
	await editor.getByRole("button", { name: "Save draft" }).click();
	await expect(page.getByRole("alert")).toContainText("Invalid configuration JSON");

	// Restore valid JSON and save draft
	await editor.getByLabel("Configuration JSON").fill(updatedJson);
	await editor.getByRole("button", { name: "Save draft" }).click();
	await expect(editor.getByText("Draft saved.")).toBeVisible();
	await expect(
		editor.getByText("Draft LLM: google / gemini-3.5-flash-lite"),
	).toBeVisible();

	// 6. Publication and activation: draft model is separate from active model
	await editor.getByRole("button", { name: "Publish draft" }).click();
	await expect(editor.getByText("Published v1.")).toBeVisible();
	await expect(editor.getByText("Local active version: none")).toBeVisible();
	await expect(editor.getByText("Local active LLM: unavailable")).toBeVisible();

	await editor
		.getByRole("listitem")
		.filter({ hasText: "v1" })
		.getByRole("button", { name: "Activate locally" })
		.click();
	await expect(editor.getByText("Local active version: 1")).toBeVisible();
	await expect(
		editor.getByText("Local active LLM: google / gemini-3.5-flash-lite"),
	).toBeVisible();

	// Editing draft to OpenAI does not change active version/LLM
	await editor.getByLabel("LLM provider").selectOption("openai");
	await editor.getByRole("button", { name: "Save draft" }).click();
	await expect(editor.getByText("Draft saved.")).toBeVisible();
	await expect(
		editor.getByText("Draft LLM: openai / gpt-4o-mini"),
	).toBeVisible();
	await expect(editor.getByText("Local active version: 1")).toBeVisible();
	await expect(
		editor.getByText("Local active LLM: google / gemini-3.5-flash-lite"),
	).toBeVisible();

	// 7. Viewer read-only behavior
	await page.route("**/api/auth/me", async (route) => {
		await route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({
				id: "viewer-synthetic-id",
				email: "viewer@example.com",
				role: "viewer",
				csrf_token: "viewer-csrf-token",
			}),
		});
	});
	await page.goto("/");
	await expect(
		page.getByText("Signed in as viewer@example.com · viewer"),
	).toBeVisible();
	const viewerEditor = page.getByRole("region", {
		name: "Agent configurations",
	});
	await expect(viewerEditor).toBeVisible();

	await viewerEditor.getByLabel("Agent").selectOption({ label: "Voice pilot" });
	await expect(
		viewerEditor.getByText("Draft LLM: openai / gpt-4o-mini"),
	).toBeVisible();
	await expect(viewerEditor.getByText("Local active version: 1")).toBeVisible();
	await expect(
		viewerEditor.getByText("Local active LLM: google / gemini-3.5-flash-lite"),
	).toBeVisible();

	await expect(
		viewerEditor.getByRole("button", { name: "Create" }),
	).not.toBeVisible();
	await expect(
		viewerEditor.getByRole("button", { name: "Save draft" }),
	).not.toBeVisible();
	await expect(
		viewerEditor.getByRole("button", { name: "Publish draft" }),
	).not.toBeVisible();
	await expect(
		viewerEditor.getByRole("button", { name: "Import JSON into draft" }),
	).not.toBeVisible();
	await expect(
		viewerEditor.getByRole("button", { name: "Activate locally" }),
	).not.toBeVisible();
	await expect(viewerEditor.getByLabel("LLM provider")).not.toBeVisible();
	await expect(viewerEditor.getByLabel("Configuration JSON")).not.toBeVisible();
});
