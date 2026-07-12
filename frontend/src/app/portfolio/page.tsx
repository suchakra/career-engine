"use client";

import { AppShell } from "@/components/AppShell";
import { PortfolioContent } from "@/app/portfolio/PortfolioContent";
import { RequireAuth } from "@/lib/auth/guard";

export default function PortfolioPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Portfolio">
        <PortfolioContent />
      </AppShell>
    </RequireAuth>
  );
}
