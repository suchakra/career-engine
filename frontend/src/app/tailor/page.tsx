"use client";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/lib/auth/guard";
import { TailorContent } from "@/app/tailor/TailorContent";

/** Tailor — JD in → ATS-safe résumé out (slice 10.6b). */
export default function TailorPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Tailor">
        <TailorContent />
      </AppShell>
    </RequireAuth>
  );
}
