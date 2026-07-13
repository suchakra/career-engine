"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Menu, User, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { SidebarNav } from "@/components/SidebarNav";
import { StatusBadge } from "@/components/StatusBadge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useAuth } from "@/lib/auth/context";
import { useKeyStatus } from "@/lib/query/hooks";
import { cn } from "@/lib/utils";

/** BYOK key indicator (§3) — live from GET /api/key. Links to Settings when absent. */
function KeyChip(): JSX.Element {
  const { data, isLoading, isError } = useKeyStatus();
  if (isLoading) return <StatusBadge status="skipped" label="Key: …" />;
  // On error, don't imply the user has no key — show a neutral "unknown" state.
  if (isError) return <StatusBadge status="review" label="Key: unknown" />;
  if (data?.has_key) return <StatusBadge status="strong" label="Key: saved" />;
  return (
    <Link href="/settings" className="rounded-full">
      <StatusBadge status="skipped" label="Add a key" />
    </Link>
  );
}

function IdentityMenu(): JSX.Element {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  // The popover holds non-menu content (email, a theme radiogroup, a button), so
  // it's a dialog — not a WAI-ARIA menu. Close on Escape or when focus leaves.
  return (
    <div
      className="relative"
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-tap items-center gap-2 rounded-card border border-border bg-surface px-2 text-sm sm:px-3"
      >
        {/* The email is the widest thing in the header. On the narrowest phones it is dropped
            entirely — the account is still reachable, and the popover shows the address. */}
        <span className="hidden max-w-[16ch] truncate sm:inline">{user?.email ?? "Account"}</span>
        <User className="h-4 w-4 sm:hidden" aria-hidden="true" />
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Account menu"
          className="absolute right-0 top-full z-20 mt-1 w-64 rounded-card border border-border bg-card p-3 shadow-lg"
        >
          <p className="mb-2 truncate text-sm text-muted" title={user?.email ?? ""}>
            {user?.email}
          </p>
          <div className="mb-3">
            <ThemeToggle />
          </div>
          <button
            type="button"
            onClick={() => void signOut()}
            className="min-h-tap w-full rounded-card border border-border px-3 text-left text-sm hover:bg-surface"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Footer(): JSX.Element {
  return (
    <footer className="border-t border-border px-6 py-3 text-center text-xs text-muted">
      <a
        href="https://github.com/bitcrafty/career-engine"
        className="hover:text-text"
        target="_blank"
        rel="noreferrer"
      >
        Open source project hosted by bitcrafty
      </a>
      {" · Engineering transformation for the AI era."}
    </footer>
  );
}

export interface AppShellProps {
  title: string;
  children: ReactNode;
}

/**
 * The nav, for phones (UX-1).
 *
 * The app shipped with **no navigation at all below `md`**: the sidebar was `hidden … md:flex`
 * and nothing replaced it — and the "CareerEngine" home link lived *inside* that hidden
 * `<aside>`. On a phone, not one route was reachable except by typing a URL.
 *
 * It renders the SAME `SidebarNav` as the desktop sidebar rather than a mobile copy, so the two
 * cannot drift — including the feature-flagged PREPARE group (AD-17.3), which a hand-maintained
 * second nav would silently miss.
 *
 * A real dialog primitive, not a hand-rolled one: focus trapping, focus restore, Escape, and
 * body-scroll lock are each individually easy to get subtly wrong (Tab wrapping, shift+Tab,
 * iOS scroll), and this is the component standing between a phone user and the whole product.
 */
function MobileNav(): JSX.Element {
  const [open, setOpen] = useState(false);

  // CLOSE THE DRAWER WHEN THE VIEWPORT CROSSES `md` — do not leave it to CSS.
  //
  // `md:hidden` hides the drawer, but hiding is not closing: `open` is React state, and a
  // modal Radix dialog that is still OPEN keeps `body { pointer-events: none }`, the
  // body-scroll lock, the focus trap, and `aria-hidden` on the rest of the app. So a phone user
  // who opens the menu and ROTATES TO LANDSCAPE (every mainstream phone crosses 768px there —
  // iPhone 14 is 844px on its side) would find the drawer gone and the app visible, scroll
  // locked, and completely unclickable: the backdrop that dismisses it is now `display:none`,
  // and there is no keyboard to press Escape. The only way out would be to reload the page —
  // worse than the bug this component exists to fix, which at least let you type a URL.
  useEffect(() => {
    const mql = window.matchMedia("(min-width: 768px)");
    const sync = (e: MediaQueryListEvent | MediaQueryList): void => {
      if (e.matches) setOpen(false);
    };
    sync(mql); // also covers mounting at desktop width with stale state
    mql.addEventListener("change", sync);
    return () => mql.removeEventListener("change", sync);
  }, []);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          aria-label="Open menu"
          data-testid="mobile-nav-trigger"
          // `md:hidden` is the whole contract of this button. If it is ever dropped, the
          // hamburger appears next to the desktop sidebar — see the class-contract test.
          className="flex min-h-tap min-w-tap items-center justify-center rounded-card border border-border px-2 md:hidden"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 md:hidden" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col gap-6 overflow-y-auto border-r border-border bg-card px-3 py-4 md:hidden"
        >
          <div className="flex items-center justify-between gap-2">
            <Dialog.Title asChild>
              <Link
                href="/dashboard"
                onClick={() => setOpen(false)}
                className="px-3 text-lg font-semibold"
              >
                CareerEngine
              </Link>
            </Dialog.Title>
            {/* A visible way out. Escape needs a keyboard, and the backdrop is an invisible
                affordance — on a 360px screen it is a 72px strip the user has to guess at. */}
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close menu"
                className="flex min-h-tap min-w-tap items-center justify-center rounded-card border border-border"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>
          {/* Tapping a link must CLOSE the drawer — otherwise the user navigates and is left
              staring at the menu they just used, on top of the page they asked for. */}
          <SidebarNav label="Mobile" onNavigate={() => setOpen(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Persistent shell: left sidebar + top bar (identity + key chips) + footer (§3). */
export function AppShell({ title, children }: AppShellProps): JSX.Element {
  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex flex-1">
        <aside
          data-testid="desktop-sidebar"
          className={cn(
            "hidden w-60 shrink-0 flex-col gap-6 border-r border-border px-3 py-4 md:flex",
          )}
        >
          <Link href="/dashboard" className="px-3 text-lg font-semibold">
            CareerEngine
          </Link>
          <SidebarNav />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          {/* At 360px this row has ~312px of usable width for a title, a key chip, an identity
              menu — and now a hamburger. It has to be allowed to shrink: `min-w-0` + `truncate`
              on the title (flex will not shrink a text node below its min-content without it),
              a tighter gutter, and the email hidden on the narrowest screens. */}
          <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3 md:px-6">
            <div className="flex min-w-0 items-center gap-2">
              <MobileNav />
              <h1 className="min-w-0 truncate text-lg font-semibold">{title}</h1>
            </div>
            <div className="flex shrink-0 items-center gap-2 md:gap-3">
              <KeyChip />
              <IdentityMenu />
            </div>
          </header>
          <main className="flex-1 px-4 py-6 md:px-6">{children}</main>
        </div>
      </div>
      <Footer />
    </div>
  );
}
