import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

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
afterEach(() => {
  vi.unstubAllGlobals();
});

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

  it("the two navs are distinct landmarks", async () => {
    // Two <nav> elements with the same accessible name are ambiguous to a screen reader — and
    // make every getByRole("link", …) throw "found multiple elements".
    //
    // The first version of this test never OPENED the drawer, so only one nav was in the DOM
    // and it passed with both navs named "Primary" — it asserted the opposite of its own name.
    // (Adversarial review.) Opening the drawer is what makes it pin anything.
    const user = userEvent.setup();
    renderWithProviders(
      <AppShell title="Dashboard">
        <p>content</p>
      </AppShell>,
    );

    await user.click(screen.getByRole("button", { name: /open menu/i }));
    await screen.findByRole("dialog");

    // `hidden: true` because a modal dialog correctly `aria-hidden`s the rest of the app — the
    // desktop nav is intentionally out of the a11y tree while the drawer is open. Both are still
    // in the DOM, and they must not share a name.
    const names = screen
      .getAllByRole("navigation", { hidden: true })
      .map((nav) => nav.getAttribute("aria-label"))
      .sort();

    expect(names).toEqual(["Mobile", "Primary"]); // fails if the `label` prop is reverted
  });

  it("CLOSES when the viewport grows past the breakpoint (the rotation freeze)", async () => {
    // THE showstopper (adversarial review). `md:hidden` HIDES the drawer at ≥768px but does not
    // CLOSE it — `open` is React state. A still-open modal Radix dialog keeps
    // `body { pointer-events: none }`, the scroll lock, and the focus trap. So a phone user who
    // opens the menu and rotates to landscape (iPhone 14 is 844px on its side — past `md`)
    // would find the drawer invisible and the app frozen: unclickable, unscrollable, with the
    // dismiss backdrop `display:none` and no keyboard for Escape. Reloading the page was the
    // only way out — worse than the bug this whole component exists to fix.
    const listeners: ((e: { matches: boolean }) => void)[] = [];
    let matches = false; // start narrow (a phone, portrait)
    vi.stubGlobal("matchMedia", (query: string) => ({
      get matches() {
        return matches;
      },
      media: query,
      addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.push(cb),
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
      onchange: null,
    }));

    const user = userEvent.setup();
    renderWithProviders(
      <AppShell title="Dashboard">
        <p>content</p>
      </AppShell>,
    );

    await user.click(screen.getByRole("button", { name: /open menu/i }));
    await screen.findByRole("dialog");

    // …the user rotates the phone.
    matches = true;
    act(() => listeners.forEach((cb) => cb({ matches: true })));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("has a visible close control", async () => {
    // A phone has no Escape key, and the backdrop is an invisible affordance — at 360px it is a
    // 72px strip the user has to guess at.
    const user = userEvent.setup();
    renderWithProviders(
      <AppShell title="Dashboard">
        <p>content</p>
      </AppShell>,
    );

    await user.click(screen.getByRole("button", { name: /open menu/i }));
    const drawer = await screen.findByRole("dialog");

    await user.click(within(drawer).getByRole("button", { name: /close menu/i }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
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
