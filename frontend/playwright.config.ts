import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E lives in its own lane (not the fast Vitest gate). Browser system
 * deps may need `npx playwright install --with-deps` on CI before this runs.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Boot the dev server for the run (skipped if PLAYWRIGHT_BASE_URL points at an
  // already-running server). The Firebase config is well-formed but fake: the SDK
  // initializes and resolves a signed-out session locally, so the landing renders
  // without a live project or a real Google popup.
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        // Static export (10.7): `next build` emits `out/`; serve it as static files
        // (`next start` is incompatible with `output: export`). A prebuilt static
        // server also avoids first-hit lazy compilation racing the assertions.
        command: "npm run build && npx --yes serve out -l 3000 --no-clipboard",
        url: "http://localhost:3000/login",
        timeout: 180_000,
        reuseExistingServer: !process.env.CI,
        env: {
          NEXT_PUBLIC_FIREBASE_API_KEY: "test-fake-api-key",
          NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: "test.firebaseapp.com",
          NEXT_PUBLIC_FIREBASE_PROJECT_ID: "test-project",
          NEXT_PUBLIC_API_BASE_URL: "http://localhost:8080",
        },
      },
});
