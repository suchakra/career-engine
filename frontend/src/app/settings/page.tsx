"use client";

import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { RequireAuth } from "@/lib/auth/guard";

/** Placeholder — BYOK key, connected accounts, consents, privacy land later. */
export default function SettingsPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Settings">
        <EmptyState
          title="Settings are coming soon"
          description="Key management, connected accounts, consents, and privacy controls arrive in a later slice."
        />
      </AppShell>
    </RequireAuth>
  );
}
