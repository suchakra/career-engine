"use client";

import { ActionCard } from "@/components/ActionCard";
import { EmptyState } from "@/components/EmptyState";
import { MetricStat } from "@/components/MetricStat";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ProfileForm } from "@/components/forms/ProfileForm";
import { PreferencesForm } from "@/components/forms/PreferencesForm";
import { useDashboard } from "@/lib/query/hooks";

/**
 * The dashboard read view (§4.1). Lives in its own module — a Next.js `page.tsx`
 * may only export the default route component, so the testable content component
 * is kept here and imported by the page + the Vitest test.
 */
export function DashboardContent(): JSX.Element {
  const { data, isLoading, isError } = useDashboard();

  if (isLoading) {
    return <p className="text-sm text-muted">Loading your dashboard…</p>;
  }

  // Load failure degrades to an EmptyState; the forms below disable Save so a
  // failed read can never silently overwrite stored data.
  const failed = isError || !data;

  return (
    <div className="flex flex-col gap-6">
      {failed ? (
        <EmptyState
          isError
          title="Couldn't load your dashboard"
          description="We couldn't reach the server. Your data is safe — saving is disabled until this loads."
        />
      ) : (
        <>
          <ActionCard title="Where you are">
            <div className="flex flex-wrap gap-8">
              <MetricStat label="Portfolio progress" value={data.progress_meter} />
              <MetricStat label="Applications" value={data.application_count} />
              <MetricStat
                label="Pending actions"
                value={data.pending_actions.length}
                caption={data.pending_actions[0]}
              />
            </div>
            {data.show_nudge && data.nudge_message && (
              <p className="mt-4 rounded-card border border-border bg-surface px-3 py-2 text-sm text-muted">
                ⓘ {data.nudge_message}
              </p>
            )}
          </ActionCard>

          <ActionCard title="Pick up where you left off">
            <div className="flex flex-wrap gap-3">
              <PrimaryButton asChild disabled={!data.can_start_grill}>
                <a href="/grill">▸ Continue grilling</a>
              </PrimaryButton>
              <PrimaryButton asChild variant="secondary">
                <a href="/tailor">Tailor a résumé</a>
              </PrimaryButton>
              <PrimaryButton asChild variant="secondary">
                <a href="/jobs">Find jobs</a>
              </PrimaryButton>
            </div>
          </ActionCard>
        </>
      )}

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Your details
        </h2>
        <ProfileForm disabled={failed} />
        <PreferencesForm disabled={failed} />
      </div>
    </div>
  );
}
