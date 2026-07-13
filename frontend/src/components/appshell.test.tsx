import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/AppShell";
import { renderWithProviders } from "@/test/utils";

// The shell reads the current route (to mark the active link) and the signed-in user.
vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/auth/context", () => ({
  useAuth: () => ({ user: { email: "jane@example.com" }, signOut: vi.fn() }),
}));

/**
 * UX-1 — the app shipped with NO navigation on a phone.
 *
 * **Read this before trusting these tests.** jsdom does not evaluate CSS and has no viewport,
 * so `md:hidden` / `hidden md:flex` are inert class *strings* here: BOTH navs are in the DOM at
 * once, and no assertion below can tell you what a 360px screen actually shows. These tests
 * prove the drawer is WIRED (it opens, it holds the links, Escape closes it, focus comes back)
 * and that the breakpoint classes are still PRESENT — the regression that caused the bug.
 *
 * They do **not** prove the app works on a phone. Nothing in CI does: the Playwright lane runs
 * signed-out (its fake Firebase config resolves to no session), so it can only ever reach
 * /login, which has no nav. Verifying real breakpoint behaviour needs an authenticated mobile
 * Playwright project — see UX-2 in GROOMING. Saying so out loud is the point: a green suite
 * that implies coverage it does not have is how an app with no mobile nav shipped in the first
 * place.
 */
describe("AppShell — mobile navigation (UX-1)", () => {
  it("has a menu button that opens a drawer containing the nav", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AppShell title="Dashboard">
        <p>content</p>
      </AppShell>,
    );

    const trigger = screen.getByRole("button", { name: /open menu/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);

    const drawer = await screen.findByRole("dialog");
    // Scoped: the desktop sidebar renders its own copy of these links in jsdom, so an unscoped
    // query would match two elements and throw.
    expect(within(drawer).getByRole("link", { name: /portfolio/i })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: /grill/i })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: /settings/i })).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AppShell title="Dashboard">
        <p>content</p>
      </AppShell>,
    );

    const trigger = screen.getByRole("button", { name: /open menu/i });
    await user.click(trigger);
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus(); // …or the user is stranded with no visible focus
  });

  it("closes when a link is tapped", async () => {
    // Otherwise the user taps "Jobs", the route changes underneath, and they are left staring
    // at the menu they just used — on top of the page they asked for.
    const user = userEvent.setup();
    renderWithProviders(
      <AppShell title="Dashboard">
        <p>content</p>
      </AppShell>,
    );

    await user.click(screen.getByRole("button", { name: /open menu/i }));
    const drawer = await screen.findByRole("dialog");
    await user.click(within(drawer).getByRole("link", { name: /jobs/i }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("the two navs are distinct landmarks", () => {
    // Two <nav> elements with the same accessible name are ambiguous to a screen reader — and
    // make every getByRole("link", …) in this file throw "found multiple elements".
    renderWithProviders(
      <AppShell title="Dashboard">
        <p>content</p>
      </AppShell>,
    );

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("keeps the breakpoint classes that decide who sees which nav", () => {
    // The ONLY thing jsdom can say about the viewport. It is a token check, not a rendering
    // check — but it is exactly the regression that caused this bug: the sidebar was
    // `hidden md:flex` with nothing replacing it below `md`. Delete either class and the app is
    // broken on one of the two form factors; this fails.
    renderWithProviders(
      <AppShell title="Dashboard">
        <p>content</p>
      </AppShell>,
    );

    expect(screen.getByTestId("mobile-nav-trigger")).toHaveClass("md:hidden");
    const sidebar = screen.getByTestId("desktop-sidebar");
    expect(sidebar).toHaveClass("hidden");
    expect(sidebar).toHaveClass("md:flex");
  });
});
