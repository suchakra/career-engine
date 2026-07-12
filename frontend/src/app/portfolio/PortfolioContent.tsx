"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ActionCard } from "@/components/ActionCard";
import { EmptyState } from "@/components/EmptyState";
import { InlineError } from "@/components/InlineError";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ResumePreview } from "@/components/ResumePreview";
import { StatusBadge, type StatusKind } from "@/components/StatusBadge";
import {
  useAddBullet,
  useDeleteBullet,
  useDeleteEntry,
  useDeleteStory,
  useEditBullet,
  useGrillEntry,
  useHighlightEntry,
  usePortfolio,
} from "@/lib/query/hooks";
import { useMasterResume } from "@/lib/tailor/useMasterResume";
import { EXPORT_FORMATS } from "@/lib/tailor/resumeExport";
import type { EntryCardResponse } from "@/lib/api/models";

/** Map the entry's display status label onto a StatusBadge kind. */
function statusKind(label: string): StatusKind {
  const l = label.toLowerCase();
  if (l.includes("document") || l.includes("strong")) return "strong";
  if (l.includes("quantif") || l.includes("review")) return "review";
  return "skipped";
}

/**
 * One experience bullet, editable in place. Reads as plain text until the user hits
 * Edit; saving PATCHes the bullet by its stable `bullet_id` (v2.9.0) and refreshes the
 * portfolio. It used to be addressed by ARRAY INDEX, which shifts under any concurrent
 * insert or delete — a slow client could edit the wrong line.
 */
function EditableBullet({
  entryId,
  bulletId,
  index,
  text,
}: {
  entryId: string;
  bulletId: string;
  index: number;
  text: string;
}): JSX.Element {
  const edit = useEditBullet();
  const remove = useDeleteBullet();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(text);

  // The <li> must stay `display: list-item` or the list-disc marker disappears — so the
  // flex row lives on an inner wrapper, not on the <li> itself.
  if (!editing) {
    return (
      <li>
        <div className="flex items-start justify-between gap-2">
          <span>{text}</span>
          <span className="flex shrink-0 gap-2">
            <button
              type="button"
              aria-label={`Edit bullet: ${text}`}
              onClick={() => {
                setDraft(text);
                setEditing(true);
              }}
              className="text-xs text-muted hover:text-text"
            >
              Edit
            </button>
            <button
              type="button"
              aria-label={`Delete bullet: ${text}`}
              disabled={remove.isPending}
              onClick={() => remove.mutate({ entryId, bulletId })}
              className="text-xs text-muted hover:text-text disabled:opacity-50"
            >
              Delete
            </button>
          </span>
        </div>
      </li>
    );
  }

  const save = (): void => {
    const next = draft.trim();
    if (!next || next === text) {
      setEditing(false);
      return;
    }
    edit.mutate(
      { entryId, bulletId, newText: next },
      { onSuccess: () => setEditing(false) },
    );
  };

  return (
    <li>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={draft}
          aria-label={`Bullet ${index + 1}`}
          maxLength={500}
          onChange={(e) => setDraft(e.target.value)}
          className="min-h-tap flex-1 rounded-card border border-border bg-surface px-2 text-sm text-text"
        />
        <PrimaryButton variant="secondary" onClick={save} disabled={edit.isPending}>
          {edit.isPending ? "Saving…" : "Save"}
        </PrimaryButton>
        <button
          type="button"
          onClick={() => setEditing(false)}
          className="text-xs text-muted hover:text-text"
        >
          Cancel
        </button>
      </div>
    </li>
  );
}

/**
 * Append a bullet to an experience the user already has, without re-grilling it.
 * Collapsed to a "+ Add a bullet" affordance until clicked, so it doesn't compete
 * with the entry's own content.
 */
function AddBullet({ entryId }: { entryId: string }): JSX.Element {
  const add = useAddBullet();
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");

  if (!adding) {
    return (
      <button
        type="button"
        onClick={() => setAdding(true)}
        className="mb-3 text-xs font-medium text-muted hover:text-text"
      >
        + Add a bullet
      </button>
    );
  }

  const save = (): void => {
    const next = text.trim();
    if (!next) {
      setAdding(false);
      return;
    }
    add.mutate(
      { entryId, text: next },
      {
        onSuccess: () => {
          setText("");
          setAdding(false);
        },
      },
    );
  };

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <input
        autoFocus
        value={text}
        maxLength={500}
        aria-label="New bullet"
        placeholder="Cut p95 latency 40%…"
        onChange={(e) => setText(e.target.value)}
        className="min-h-tap flex-1 rounded-card border border-border bg-surface px-2 text-sm text-text placeholder:text-muted"
      />
      <PrimaryButton variant="secondary" onClick={save} disabled={add.isPending}>
        {add.isPending ? "Adding…" : "Add"}
      </PrimaryButton>
      <button
        type="button"
        onClick={() => setAdding(false)}
        className="text-xs text-muted hover:text-text"
      >
        Cancel
      </button>
    </div>
  );
}

/**
 * A single portfolio entry with its parity actions (§4.4): grill this entry,
 * pin/unpin it (always tailored), edit + add bullets, and delete individual STAR
 * stories. The action mutations live in this component so each card manages its
 * own pending state.
 */
function EntryCard({ entry }: { entry: EntryCardResponse }): JSX.Element {
  const router = useRouter();
  const grill = useGrillEntry();
  const highlight = useHighlightEntry();
  const deleteStory = useDeleteStory();
  const deleteEntry = useDeleteEntry();
  const [confirming, setConfirming] = useState(false);

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
        <ul className="mb-2 list-disc space-y-1 pl-5 text-sm">
          {entry.bullets.map((b, i) => (
            <EditableBullet
              key={b.bullet_id}
              entryId={entry.entry_id}
              bulletId={b.bullet_id}
              index={i}
              text={b.text}
            />
          ))}
        </ul>
      )}
      <AddBullet entryId={entry.entry_id} />
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
        {/* Deleting an experience CASCADES to its STAR stories on the server, so it
            destroys grilled work — it gets a confirm step, unlike the other actions. */}
        {confirming ? (
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted">
              Delete this experience and its {entry.story_count} STAR{" "}
              {entry.story_count === 1 ? "story" : "stories"}?
            </span>
            <PrimaryButton
              variant="secondary"
              disabled={deleteEntry.isPending}
              onClick={() => deleteEntry.mutate(entry.entry_id)}
            >
              {deleteEntry.isPending ? "Deleting…" : "Yes, delete"}
            </PrimaryButton>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="text-xs text-muted hover:text-text"
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            type="button"
            aria-label={`Delete experience: ${entry.title}`}
            onClick={() => setConfirming(true)}
            className="min-h-tap text-xs text-muted hover:text-text"
          >
            Delete experience
          </button>
        )}
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
            {EXPORT_FORMATS.map(({ fmt, label }) => (
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
