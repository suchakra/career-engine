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
  /** `edited` → PATCH the old text back. `created` → DELETE the bullet we made, and the
   *  assembler falls back to the story's own line, which is what was there before. */
  kind: "edited" | "created";
  bulletId: string;
  /** The text the PORTFOLIO had, snapshotted when the server tailored this résumé — never
   *  the preview's current text, which a "this résumé only" edit may already have changed. */
  original: string;
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
  // One undo per LINE, not one slot for the whole page: overwriting a second line must not
  // quietly make the first one unrecoverable while the UI still offers to undo it.
  const [undos, setUndos] = useState<Map<string, UndoableOverwrite>>(new Map());

  const remember = (key: string, u: UndoableOverwrite): void =>
    setUndos((prev) => new Map(prev).set(key, u));

  /** Persist (or don't) one edited line, per the destination the user picked. */
  const saveLine = async (edit: LineEdit): Promise<void> => {
    const { entryId, key, line, text, destination } = edit;
    // What the PORTFOLIO says, captured when the server tailored this résumé — NOT the current
    // preview text, which a "this résumé only" edit may already have changed. Undoing to the
    // preview would write a JD-specific wording into the master that the user explicitly chose
    // not to persist: an undo that makes things worse than not undoing.
    const original = tailor.originalText(key);

    // "This résumé only" — the export and the tracked application both serialize the résumé
    // held in `useTailor`, so updating it there IS the whole implementation. Deliberately
    // zero API calls: the portfolio must not learn about a JD-specific rewording.
    tailor.editLine(key, text);
    if (destination === "resume-only") return;

    setBusyKey(key);
    try {
      if (line.bullet_id) {
        // In place, keeping the bullet_id — so the story link, the coverage state and the
        // résumé de-dup all keep pointing at the right line. (NOT `supersedes`: that mints a
        // new bullet which coverage reads as uncovered, and the grill would re-open a
        // finished entry to demand a number for the line the user just polished.)
        await editBullet.mutateAsync({ entryId, bulletId: line.bullet_id, newText: text });
        remember(key, { entryId, kind: "edited", bulletId: line.bullet_id, original });
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
        tailor.identifyLine(key, bullet_id);
        remember(key, { entryId, kind: "created", bulletId: bullet_id, original });
      }
    } catch {
      tailor.editLine(key, line.text); // roll the preview back
    } finally {
      setBusyKey(null);
    }
  };

  /** Put the portfolio back. Overwrite is destructive — the old wording is GONE from the
   *  store — so a user who rewords a line for one job and regrets it has no other way back. */
  const undoOverwrite = async (key: string): Promise<void> => {
    const u = undos.get(key);
    if (!u) return;
    setBusyKey(key);
    try {
      if (u.kind === "edited") {
        await editBullet.mutateAsync({
          entryId: u.entryId,
          bulletId: u.bulletId,
          newText: u.original,
        });
      } else {
        // Deleting the bullet we created makes the assembler fall back to the story's own
        // text — which is exactly the line that was there before.
        await deleteBullet.mutateAsync({ entryId: u.entryId, bulletId: u.bulletId });
        // …and the line must STOP claiming that bullet, which no longer exists. Otherwise its
        // next overwrite would PATCH a dead id: the store logs "not found", the route still
        // answers 204, and the UI reports success while nothing is written — forever.
        tailor.identifyLine(key, "");
      }
      tailor.editLine(key, u.original);
      setUndos((prev) => {
        const next = new Map(prev);
        next.delete(key);
        return next;
      });
      showToast("Put that line back.", "success");
    } catch {
      showToast("Couldn't undo that — try again.", "error");
    } finally {
      setBusyKey(null);
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
            {/* Undo is offered PER LINE (see ResumePreview), not as one page-level slot: a
                second overwrite must not quietly strand the first one's original text. */}
            <ResumePreview
              resume={tailor.resume}
              onEditLine={saveLine}
              onEditSummary={tailor.editSummary}
              onUndo={undoOverwrite}
              persistedKeys={new Set(undos.keys())}
              busyKey={busyKey}
            />
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
