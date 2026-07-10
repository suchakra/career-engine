"use client";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/lib/auth/guard";
import { GrillContent } from "@/app/grill/GrillContent";

/** The interactive grill (streaming) — slice 10.6. */
export default function GrillPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Grill">
        <GrillContent />
      </AppShell>
    </RequireAuth>
  );
}
