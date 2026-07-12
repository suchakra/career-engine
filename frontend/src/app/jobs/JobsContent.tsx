"use client";

import { ActionCard } from "@/components/ActionCard";
import { EmptyState } from "@/components/EmptyState";
import { PrimaryButton } from "@/components/PrimaryButton";
import { StatusBadge, type StatusKind } from "@/components/StatusBadge";
import { useDiscoverJobs, useDismissCompany, useJobs } from "@/lib/query/hooks";
import type { JobCardResponse } from "@/lib/api/models";

function JobTile({ job, status }: { job: JobCardResponse; status: StatusKind }): JSX.Element {
  // "Not interested" is a HITL signal on the COMPANY (that is what the discovery ledger
  // records), so future runs hard-reject it — not just this one posting.
  const dismiss = useDismissCompany();
  return (
    <ActionCard
      title={`${job.title} — ${job.company}`}
      headerRight={<StatusBadge status={status} label={job.status} />}
    >
      <p className="mb-1 text-sm text-muted">
        {job.location} · {job.work_model} · {job.employment_type}
      </p>
      {job.rationale && <p className="text-sm">{job.rationale}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-3">
        {job.url && (
          <a href={job.url} target="_blank" rel="noreferrer" className="text-sm text-primary">
            View posting ↗
          </a>
        )}
        <button
          type="button"
          disabled={dismiss.isPending}
          onClick={() => dismiss.mutate(job.company)}
          title={`Stop suggesting jobs at ${job.company}`}
          className="min-h-tap rounded-card text-sm text-muted hover:text-text disabled:opacity-50"
        >
          {dismiss.isPending ? "Dismissing…" : "Not interested"}
        </button>
      </div>
    </ActionCard>
  );
}

function FindJobsBar(): JSX.Element {
  const discover = useDiscoverJobs();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted">
        Live discovery, ranked against your saved rubric (runs on your Gemini key).
      </p>
      <PrimaryButton onClick={() => discover.mutate()} disabled={discover.isPending}>
        {discover.isPending ? "Searching…" : "▸ Find jobs"}
      </PrimaryButton>
    </div>
  );
}

/** Jobs (§4.4) — live discovery run + two-tier results. */
export function JobsContent(): JSX.Element {
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
      <div className="flex flex-col gap-6">
        <FindJobsBar />
        <EmptyState
          title="No job matches yet"
          description={data.empty_text || "Set your rubric on the Dashboard, then hit Find jobs."}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <FindJobsBar />
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
