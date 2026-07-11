"use client";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/lib/auth/guard";
import { SettingsContent } from "@/app/settings/SettingsContent";

/** Settings — BYOK key + appearance (parity P1). */
export default function SettingsPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Settings">
        <SettingsContent />
      </AppShell>
    </RequireAuth>
  );
}
