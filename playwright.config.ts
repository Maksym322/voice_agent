import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  use: {
    baseURL: process.env.VF_E2E_URL,
    browserName: "chromium",
  },
  retries: 0,
  workers: 1,
});

