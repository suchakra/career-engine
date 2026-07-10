"use client";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/lib/auth/guard";
import { DashboardContent } from "@/app/dashboard/DashboardContent";

export default function DashboardPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Dashboard">
        <DashboardContent />
      </AppShell>
    </RequireAuth>
  );
}
