"use client";

import { useRouter } from "next/navigation";

import { ActionCard } from "@/components/ActionCard";
import { EmptyState } from "@/components/EmptyState";
import { InlineError } from "@/components/InlineError";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ResumePreview } from "@/components/ResumePreview";
import { StatusBadge, type StatusKind } from "@/components/StatusBadge";
import {
  useDeleteStory,
  useGrillEntry,
  useHighlightEntry,
  usePortfolio,
} from "@/lib/query/hooks";
import { useMasterResume } from "@/lib/tailor/useMasterResume";
import type { ExportFormat } from "@/lib/tailor/resumeExport";
import type { EntryCardResponse } from "@/lib/api/models";

const FORMATS: { fmt: ExportFormat; label: string }[] = [
  { fmt: "pdf", label: "PDF" },
  { fmt: "docx", label: "Word" },
  { fmt: "md", label: "Markdown" },
];

/** Map the entry's display status label onto a StatusBadge kind. */
function statusKind(label: string): StatusKind {
  const l = label.toLowerCase();
  if (l.includes("document") || l.includes("strong")) return "strong";
  if (l.includes("quantif") || l.includes("review")) return "review";
  return "skipped";
}

/**
 * A single portfolio entry with its parity actions (§4.4): grill this entry,
 * pin/unpin it (always tailored), and delete individual STAR stories. The action
 * mutations live in this component so each card manages its own pending state.
 */
function EntryCard({ entry }: { entry: EntryCardResponse }): JSX.Element {
  const router = useRouter();
  const grill = useGrillEntry();
  const highlight = useHighlightEntry();
  const deleteStory = useDeleteStory();

  return (
    <ActionCard
      title={`${entry.title} — ${entry.org}`}
      headerRight={
        <StatusBadge status={statusKind(entry.status_label)} label={entry.status_label} />
      }
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
              <li key={s.story_id} className="flex items-start justify-between gap-2">
                <span>
                  <span className="font-medium">S:</span> {s.situation}{" "}
                  <span className="font-medium">R:</span> {s.result}{" "}
                  {s.metric_validated && <StatusBadge status="strong" label="Metric" />}
                </span>
                <button
                  type="button"
                  aria-label={`Delete story: ${s.situation}`}
                  disabled={deleteStory.isPending}
                  onClick={() => deleteStory.mutate(s.story_id)}
                  className="min-h-tap shrink-0 rounded-card px-2 text-xs text-muted hover:text-text disabled:opacity-50"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <PrimaryButton
          variant="secondary"
          disabled={grill.isPending}
          onClick={() =>
            grill.mutate(entry.entry_id, { onSuccess: () => router.push("/grill") })
          }
        >
          {grill.isPending ? "Starting…" : "Grill me about this"}
        </PrimaryButton>
        <PrimaryButton
          variant="secondary"
          disabled={highlight.isPending}
          onClick={() =>
            highlight.mutate({ entryId: entry.entry_id, highlighted: !entry.highlighted })
          }
        >
          {entry.highlighted ? "★ Pinned" : "☆ Pin"}
        </PrimaryButton>
      </div>
    </ActionCard>
  );
}

/**
 * Master résumé (§4.4): assemble every validated achievement — no JD, no model call,
 * no BYOK key — then preview and export it through the same renderer as the Tailor.
 */
function MasterResumeCard(): JSX.Element {
  const master = useMasterResume();
  return (
    <ActionCard title="Master résumé">
      <p className="mb-3 text-sm text-muted">
        Every quantified achievement you&apos;ve documented, in one résumé — no job
        description needed. Tailor it to a specific role over on Tailor.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <PrimaryButton onClick={() => void master.build()} disabled={master.building}>
          {master.building ? "Building…" : "Build master résumé"}
        </PrimaryButton>
        {master.resume && (
          <>
            <span className="text-sm text-muted">Export:</span>
            {FORMATS.map(({ fmt, label }) => (
              <PrimaryButton
                key={fmt}
                variant="secondary"
                onClick={() => void master.exportResume(fmt)}
                disabled={master.exporting !== null}
              >
                {master.exporting === fmt ? "…" : label}
              </PrimaryButton>
            ))}
          </>
        )}
      </div>
      {master.error && <InlineError message={master.error} />}
      {master.resume && (
        <div className="mt-3">
          <ResumePreview resume={master.resume} />
        </div>
      )}
    </ActionCard>
  );
}

/**
 * The portfolio read view + entry actions (§4.4). Extracted from `page.tsx` so it
 * is directly testable (a Next.js `page.tsx` may only export the route component).
 */
export function PortfolioContent(): JSX.Element {
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
      <MasterResumeCard />
      {data.entries.map((entry) => (
        <EntryCard key={entry.entry_id} entry={entry} />
      ))}
    </div>
  );
}
