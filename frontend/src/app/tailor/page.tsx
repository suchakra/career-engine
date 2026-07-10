"use client";

import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { RequireAuth } from "@/lib/auth/guard";

/** Placeholder — the JD-in / résumé-out tailor flow is built in a later slice. */
export default function TailorPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Tailor">
        <EmptyState
          title="Tailor is coming soon"
          description="Paste a job description to get an ATS-safe résumé — arriving in a later slice."
        />
      </AppShell>
    </RequireAuth>
  );
}
