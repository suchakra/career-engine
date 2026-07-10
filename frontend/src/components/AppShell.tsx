"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { SidebarNav } from "@/components/SidebarNav";
import { StatusBadge } from "@/components/StatusBadge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useAuth } from "@/lib/auth/context";
import { cn } from "@/lib/utils";

/** BYOK key indicator states (§3). No live key source in 10.5 → defaults to "add a key". */
type KeyState = "saved" | "session" | "none";

function KeyChip({ state }: { state: KeyState }): JSX.Element {
  if (state === "saved") return <StatusBadge status="strong" label="Key: saved" />;
  if (state === "session") return <StatusBadge status="review" label="Key: this session only" />;
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
        className="flex min-h-tap items-center gap-2 rounded-card border border-border bg-surface px-3 text-sm"
      >
        <span className="max-w-[16ch] truncate">{user?.email ?? "Account"}</span>
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
  keyState?: KeyState;
}

/** Persistent shell: left sidebar + top bar (identity + key chips) + footer (§3). */
export function AppShell({ title, children, keyState = "none" }: AppShellProps): JSX.Element {
  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex flex-1">
        <aside
          className={cn(
            "hidden w-60 shrink-0 flex-col gap-6 border-r border-border px-3 py-4 md:flex",
          )}
        >
          <Link href="/dashboard" className="px-3 text-lg font-semibold">
            CareerEngine
          </Link>
          <SidebarNav />
        </aside>

        <div className="flex flex-1 flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-border px-6 py-3">
            <h1 className="text-lg font-semibold">{title}</h1>
            <div className="flex items-center gap-3">
              <KeyChip state={keyState} />
              <IdentityMenu />
            </div>
          </header>
          <main className="flex-1 px-6 py-6">{children}</main>
        </div>
      </div>
      <Footer />
    </div>
  );
}
