"use client";

import { useState } from "react";

import { ActionCard } from "@/components/ActionCard";
import { InlineError } from "@/components/InlineError";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ResumePreview, type LineEdit } from "@/components/ResumePreview";
import type { StructuredResume } from "@/lib/api/models";
import {
  useAddBullet,
  useDeleteBullet,
  useEditBullet,
  useTrackApplication,
} from "@/lib/query/hooks";
import { EXPORT_FORMATS } from "@/lib/tailor/resumeExport";
import { useTailor } from "@/lib/tailor/useTailor";
import { useToast } from "@/components/Toast";

const INPUT_CLASS =
  "min-h-tap w-40 max-w-full rounded-card border border-border bg-surface px-3 text-sm text-text placeholder:text-muted";

/** Enough to put the portfolio back exactly as it was. */
interface UndoableOverwrite {
  entryId: string;
  key: string;
  /** `edited` → PATCH the old text back. `created` → DELETE the bullet we made, and the
   *  assembler falls back to the story's own line, which is what was there before. */
  kind: "edited" | "created";
  bulletId: string;
  previous: string;
}

function TrackApplicationCard({ resume, jd }: { resume: StructuredResume; jd: string }): JSX.Element {
  const track = useTrackApplication();
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const canSave = Boolean(company.trim() && role.trim());
  return (
    <ActionCard title="Track as application">
      <p className="mb-2 text-sm text-muted">
        Save this tailored résumé against a company + role — it appears on your Dashboard.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <input
          className={INPUT_CLASS}
          value={company}
          placeholder="Company"
          aria-label="Company"
          onChange={(e) => setCompany(e.target.value)}
        />
        <input
          className={INPUT_CLASS}
          value={role}
          placeholder="Role"
          aria-label="Role"
          onChange={(e) => setRole(e.target.value)}
        />
        <PrimaryButton
          variant="secondary"
          disabled={!canSave || track.isPending}
          onClick={() =>
            track.mutate(
              {
                company: company.trim(),
                job_title: role.trim(),
                jd_text: jd,
                tailored_resume_json: JSON.stringify(resume),
              },
              {
                onSuccess: () => {
                  setCompany("");
                  setRole("");
                },
              },
            )
          }
        >
          {track.isPending ? "Saving…" : "Save as tracked application"}
        </PrimaryButton>
      </div>
    </ActionCard>
  );
}

/**
 * Tailor (§4.5): paste a JD → one model call selects JD-relevant achievements and
 * writes a tailored summary/skills → preview → export (PDF/Word/Markdown). Two-pane
 * on desktop, stacked on mobile.
 */
export function TailorContent(): JSX.Element {
  const tailor = useTailor();
  const addBullet = useAddBullet();
  const editBullet = useEditBullet();
  const deleteBullet = useDeleteBullet();
  const { showToast } = useToast();
  const [jd, setJd] = useState("");
  const [instructions, setInstructions] = useState("");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [undo, setUndo] = useState<UndoableOverwrite | null>(null);
  const [undoing, setUndoing] = useState(false);

  /** Persist (or don't) one edited line, per the destination the user picked. */
  const saveLine = async (edit: LineEdit): Promise<void> => {
    const { entryId, key, line, text, destination } = edit;

    // "This résumé only" — the export and the tracked application both serialize the résumé
    // held in `useTailor`, so updating it there IS the whole implementation. Deliberately
    // zero API calls: the portfolio must not learn about a JD-specific rewording.
    tailor.editLine(entryId, key, text);
    if (destination === "resume-only") return;

    setBusyKey(key);
    try {
      if (line.bullet_id) {
        // In place, keeping the bullet_id — so the story link, the coverage state and the
        // résumé de-dup all keep pointing at the right line. (NOT `supersedes`: that mints a
        // new bullet which coverage reads as uncovered, and the grill would re-open a
        // finished entry to demand a number for the line the user just polished.)
        await editBullet.mutateAsync({ entryId, bulletId: line.bullet_id, newText: text });
        setUndo({ entryId, key, kind: "edited", bulletId: line.bullet_id, previous: line.text });
      } else if (line.story_id) {
        // The grill wrote this line and the copywriter never polished it, so there is no
        // bullet yet. Create one that SPEAKS FOR the story; the assembler then renders it in
        // place of the raw story text.
        const { bullet_id } = await addBullet.mutateAsync({
          entryId,
          text,
          derivedFromStoryId: line.story_id,
        });
        // Adopt the id, or the user's next edit would try to create a SECOND bullet for this
        // story and be refused — locking them out of fixing a typo they just introduced.
        tailor.identifyLine(entryId, key, bullet_id);
        setUndo({ entryId, key, kind: "created", bulletId: bullet_id, previous: line.text });
      }
    } catch {
      tailor.editLine(entryId, key, line.text); // roll the preview back to what was saved
    } finally {
      setBusyKey(null);
    }
  };

  /** Put the portfolio back. Overwrite is destructive — the old wording is GONE from the
   *  store — so a user who rewords a line for one job and regrets it has no other way back. */
  const undoOverwrite = async (): Promise<void> => {
    if (!undo) return;
    setUndoing(true);
    try {
      if (undo.kind === "edited") {
        await editBullet.mutateAsync({
          entryId: undo.entryId,
          bulletId: undo.bulletId,
          newText: undo.previous,
        });
      } else {
        // Deleting the bullet we created makes the assembler fall back to the story's own
        // text — which is exactly the line that was there before.
        await deleteBullet.mutateAsync({ entryId: undo.entryId, bulletId: undo.bulletId });
      }
      tailor.editLine(undo.entryId, undo.key, undo.previous);
      setUndo(null);
      showToast("Put that line back.", "success");
    } catch {
      showToast("Couldn't undo that — try again.", "error");
    } finally {
      setUndoing(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <div className="flex flex-1 flex-col gap-3">
        <label className="text-sm font-medium" htmlFor="jd">
          Job description
        </label>
        <textarea
          id="jd"
          className="min-h-[12rem] w-full resize-y rounded-card border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-muted"
          value={jd}
          placeholder="Paste the job description here…"
          onChange={(e) => setJd(e.target.value)}
        />
        <label className="text-sm font-medium" htmlFor="instructions">
          Specific instructions <span className="text-muted">(optional, not saved to your profile)</span>
        </label>
        <input
          id="instructions"
          className="min-h-tap w-full rounded-card border border-border bg-surface px-3 text-sm text-text placeholder:text-muted"
          value={instructions}
          maxLength={500}
          placeholder="Emphasise cloud. Omit side projects."
          onChange={(e) => setInstructions(e.target.value)}
        />
        <div>
          <PrimaryButton
            onClick={() => void tailor.tailor({ jd_text: jd, instructions, contact: null })}
            disabled={!jd.trim() || tailor.tailoring}
          >
            {tailor.tailoring ? "Tailoring…" : "✦ Tailor my résumé"}
          </PrimaryButton>
        </div>
        {tailor.error && <InlineError message={tailor.error} />}
      </div>

      <div className="flex flex-1 flex-col gap-3">
        {tailor.resume ? (
          <>
            <ResumePreview
              resume={tailor.resume}
              onEditLine={saveLine}
              onEditSummary={tailor.editSummary}
              busyKey={busyKey}
            />
            {undo && (
              <div className="flex items-center justify-between gap-2 rounded-card border border-border bg-surface px-3 py-2 text-sm">
                <span className="text-muted">Replaced a line in your portfolio.</span>
                <button
                  type="button"
                  onClick={() => void undoOverwrite()}
                  disabled={undoing}
                  className="min-h-tap rounded-card border border-border px-3 text-sm hover:bg-card"
                >
                  {undoing ? "Undoing…" : "Undo"}
                </button>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted">Export:</span>
              {EXPORT_FORMATS.map(({ fmt, label }) => (
                <PrimaryButton
                  key={fmt}
                  variant="secondary"
                  onClick={() => void tailor.exportResume(fmt)}
                  disabled={tailor.exporting !== null}
                >
                  {tailor.exporting === fmt ? "…" : label}
                </PrimaryButton>
              ))}
            </div>
            <TrackApplicationCard resume={tailor.resume} jd={jd} />
          </>
        ) : (
          <ActionCard title="Preview">
            <p className="text-sm text-muted">
              Paste a job description and tailor your résumé to see the preview here.
            </p>
          </ActionCard>
        )}
      </div>
    </div>
  );
}
