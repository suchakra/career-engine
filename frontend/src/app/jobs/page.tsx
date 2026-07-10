"use client";

import { ActionCard } from "@/components/ActionCard";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge, type StatusKind } from "@/components/StatusBadge";
import { RequireAuth } from "@/lib/auth/guard";
import { useJobs } from "@/lib/query/hooks";
import type { JobCardResponse } from "@/lib/api/models";

function JobTile({ job, status }: { job: JobCardResponse; status: StatusKind }): JSX.Element {
  return (
    <ActionCard
      title={`${job.title} — ${job.company}`}
      headerRight={<StatusBadge status={status} label={job.status} />}
    >
      <p className="mb-1 text-sm text-muted">
        {job.location} · {job.work_model} · {job.employment_type}
      </p>
      {job.rationale && <p className="text-sm">{job.rationale}</p>}
      {job.url && (
        <a href={job.url} target="_blank" rel="noreferrer" className="text-sm text-primary">
          View posting ↗
        </a>
      )}
    </ActionCard>
  );
}

function JobsContent(): JSX.Element {
  const { data, isLoading, isError } = useJobs();

  if (isLoading) return <p className="text-sm text-muted">Loading job matches…</p>;

  if (isError || !data) {
    return (
      <EmptyState
        isError
        title="Couldn't load job matches"
        description="We couldn't reach the server. Your data is safe."
      />
    );
  }

  if (data.is_empty) {
    return (
      <EmptyState
        title="No job matches yet"
        description={data.empty_text || "Run discovery to find roles ranked against your rubric."}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Accepted ({data.accepted.length})
        </h2>
        {data.accepted.map((job) => (
          <JobTile key={job.job_id} job={job} status="strong" />
        ))}
      </section>
      {data.for_review.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
            For review ({data.for_review.length})
          </h2>
          {data.for_review.map((job) => (
            <JobTile key={job.job_id} job={job} status="review" />
          ))}
        </section>
      )}
    </div>
  );
}

export default function JobsPage(): JSX.Element {
  return (
    <RequireAuth>
      <AppShell title="Jobs">
        <JobsContent />
      </AppShell>
    </RequireAuth>
  );
}
