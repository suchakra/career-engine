"use client";

import { useState } from "react";

import { PrimaryButton } from "@/components/PrimaryButton";
import { useAcceptBullets, useCopywrite } from "@/lib/query/hooks";
import type { CopyProposalResponse } from "@/lib/api/models";

/**
 * The copywriter loop (CQ-4 / AD-18.2). Asks the model to rewrite this experience's bullets
 * — one call for the whole entry — then shows each proposal NEXT TO its original so the user
 * can accept, edit, or reject it.
 *
 * Nothing reaches the résumé unreviewed: only what the user accepts is persisted, and because
 * it IS persisted, résumé export needs no model call at all.
 */
export function CopywriterPanel({ entryId }: { entryId: string }): JSX.Element {
  const draft = useCopywrite();
  const save = useAcceptBullets();

  const [proposals, setProposals] = useState<CopyProposalResponse[] | null>(null);
  // Keyed by source_id. Absent = rejected; present = accepted with this (possibly edited) text.
  const [accepted, setAccepted] = useState<Record<string, string>>({});

  const start = (): void => {
    draft.mutate(entryId, {
      onSuccess: (data) => {
        setProposals(data.proposals);
        // Default to accepting every proposal as drafted — rejecting is the deliberate act.
        setAccepted(
          Object.fromEntries(data.proposals.map((p) => [p.source_id, p.text])),
        );
      },
    });
  };

  const reject = (sourceId: string): void =>
    setAccepted((prev) => {
      const next = { ...prev };
      delete next[sourceId];
      return next;
    });

  if (proposals === null) {
    return (
      <PrimaryButton variant="secondary" disabled={draft.isPending} onClick={start}>
        {draft.isPending ? "Drafting…" : "✦ Polish these bullets"}
      </PrimaryButton>
    );
  }

  if (proposals.length === 0) {
    return (
      <p className="text-sm text-muted">
        Nothing to polish here yet — grill this experience or add a bullet first.
      </p>
    );
  }

  const acceptedCount = Object.keys(accepted).length;

  return (
    <div className="flex flex-col gap-3 rounded-card border border-border bg-surface p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">
        Proposed rewrites — accept, edit, or reject each
      </p>

      {proposals.map((p) => {
        const isAccepted = p.source_id in accepted;
        return (
          <div key={p.source_id} className="flex flex-col gap-1 border-t border-border pt-2">
            {p.original && (
              <p className="text-xs text-muted line-through">{p.original}</p>
            )}
            <textarea
              value={accepted[p.source_id] ?? p.text}
              disabled={!isAccepted}
              aria-label={`Rewritten bullet for: ${p.original || p.text}`}
              maxLength={500}
              onChange={(e) =>
                setAccepted((prev) => ({ ...prev, [p.source_id]: e.target.value }))
              }
              className="min-h-[3rem] w-full resize-y rounded-card border border-border bg-card px-2 py-1 text-sm text-text disabled:opacity-40"
            />
            <div className="flex gap-3">
              {isAccepted ? (
                <button
                  type="button"
                  aria-label={`Reject rewrite: ${p.text}`}
                  onClick={() => reject(p.source_id)}
                  className="text-xs text-muted hover:text-text"
                >
                  Reject
                </button>
              ) : (
                <button
                  type="button"
                  aria-label={`Accept rewrite: ${p.text}`}
                  onClick={() =>
                    setAccepted((prev) => ({ ...prev, [p.source_id]: p.text }))
                  }
                  className="text-xs text-muted hover:text-text"
                >
                  Accept
                </button>
              )}
            </div>
          </div>
        );
      })}

      <div className="flex flex-wrap items-center gap-2">
        <PrimaryButton
          disabled={acceptedCount === 0 || save.isPending}
          onClick={() =>
            save.mutate(
              {
                entryId,
                accepted: Object.entries(accepted).map(([source_id, text]) => ({
                  source_id,
                  text,
                })),
              },
              { onSuccess: () => setProposals(null) },
            )
          }
        >
          {save.isPending ? "Saving…" : `Keep ${acceptedCount} rewrite${acceptedCount === 1 ? "" : "s"}`}
        </PrimaryButton>
        <button
          type="button"
          onClick={() => setProposals(null)}
          className="text-xs text-muted hover:text-text"
        >
          Discard all
        </button>
      </div>
    </div>
  );
}
