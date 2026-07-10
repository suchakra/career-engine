import { expect, test } from "@playwright/test";

/**
 * Login / landing smoke (§4.0) — "one obvious way in".
 *
 * This is a real-browser smoke test: it boots the built app (Playwright's
 * webServer, see playwright.config.ts) with a well-formed-but-fake Firebase
 * config so the SDK initializes and resolves to a signed-out session locally
 * (no network, no real Google popup). We assert the public landing renders its
 * single primary CTA and brand chrome — not that sign-in itself works (that
 * needs a live Firebase project and is out of scope for the shell slice).
 */
test.describe("Login / landing", () => {
  test("renders the bitcrafty-branded landing with a single sign-in CTA", async ({
    page,
  }) => {
    await page.goto("/login");

    // Brand chrome: bitcrafty wordmark + tagline, product identity below.
    // Exact match targets the standalone wordmark, not the footer attribution.
    await expect(page.getByText("bitcrafty", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "CareerEngine" }),
    ).toBeVisible();

    // One obvious way in: the single primary CTA.
    await expect(
      page.getByRole("button", { name: /sign in with google/i }),
    ).toBeVisible();

    // Privacy one-liner sets the BYOK/privacy expectation before login.
    await expect(page.getByText(/bring your own gemini key/i)).toBeVisible();

    // Persistent footer carries the open-source / bitcrafty attribution.
    await expect(
      page.getByRole("link", { name: /open source project hosted by bitcrafty/i }),
    ).toBeVisible();
  });

  test("visiting a protected route while signed out lands on login", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    // RequireAuth redirects unauthenticated users to /login.
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole("button", { name: /sign in with google/i }),
    ).toBeVisible();
  });
});
