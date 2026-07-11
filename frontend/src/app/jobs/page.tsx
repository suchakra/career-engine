"use client";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/lib/auth/guard";
import { JobsContent } from "@/app/jobs/JobsContent";

/** Jobs — live discovery + ranked matches (parity P2). */
export default function JobsPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Jobs">
        <JobsContent />
      </AppShell>
    </RequireAuth>
  );
}
