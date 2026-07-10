"use client";

import { ActionCard } from "@/components/ActionCard";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { PrimaryButton } from "@/components/PrimaryButton";
import { StatusBadge, type StatusKind } from "@/components/StatusBadge";
import { RequireAuth } from "@/lib/auth/guard";
import { usePortfolio } from "@/lib/query/hooks";
import type { EntryCardResponse } from "@/lib/api/models";

/** Map the entry's display status label onto a StatusBadge kind. */
function statusKind(label: string): StatusKind {
  const l = label.toLowerCase();
  if (l.includes("document") || l.includes("strong")) return "strong";
  if (l.includes("quantif") || l.includes("review")) return "review";
  return "skipped";
}

function EntryCard({ entry }: { entry: EntryCardResponse }): JSX.Element {
  return (
    <ActionCard
      title={`${entry.title} — ${entry.org}`}
      headerRight={<StatusBadge status={statusKind(entry.status_label)} label={entry.status_label} />}
    >
      <p className="mb-2 text-sm text-muted">
        {entry.dates} · {entry.type_label}
      </p>
      {entry.bullets.length > 0 && (
        <ul className="mb-3 list-disc pl-5 text-sm">
          {entry.bullets.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      )}
      {entry.stories.length > 0 && (
        <div className="rounded-card border border-border bg-surface p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            STAR stories ({entry.story_count})
          </p>
          <ul className="flex flex-col gap-2 text-sm">
            {entry.stories.map((s) => (
              <li key={s.story_id}>
                <span className="font-medium">S:</span> {s.situation}{" "}
                <span className="font-medium">R:</span> {s.result}{" "}
                {s.metric_validated && <StatusBadge status="strong" label="Metric" />}
              </li>
            ))}
          </ul>
        </div>
      )}
    </ActionCard>
  );
}

function PortfolioContent(): JSX.Element {
  const { data, isLoading, isError } = usePortfolio();

  if (isLoading) return <p className="text-sm text-muted">Loading your portfolio…</p>;

  if (isError || !data) {
    return (
      <EmptyState
        isError
        title="Couldn't load your portfolio"
        description="We couldn't reach the server. Your data is safe."
      />
    );
  }

  if (data.is_empty) {
    return (
      <EmptyState
        title="Nothing recorded yet"
        description={data.empty_text || "Start a Grill to capture your first experience."}
        action={
          <PrimaryButton asChild>
            <a href="/grill">Start grilling</a>
          </PrimaryButton>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {data.entries.map((entry) => (
        <EntryCard key={entry.entry_id} entry={entry} />
      ))}
    </div>
  );
}

export default function PortfolioPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Portfolio">
        <PortfolioContent />
      </AppShell>
    </RequireAuth>
  );
}
