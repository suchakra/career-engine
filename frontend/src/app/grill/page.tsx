"use client";

import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { RequireAuth } from "@/lib/auth/guard";

/** Placeholder — the interactive grill (SSE) is built in slice 10.6. */
export default function GrillPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Grill">
        <EmptyState
          title="Grill is coming soon"
          description="The interactive grill (streaming transcript) arrives in a later slice."
        />
      </AppShell>
    </RequireAuth>
  );
}
