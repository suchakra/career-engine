"use client";

import { useState } from "react";

import type { ResumeLine, RoleBlock, StructuredResume } from "@/lib/api/models";
import { lineKey } from "@/lib/tailor/useTailor";

/** What the user chose to do with an edit (CQ-6b / AD-18.4). */
export type EditDestination = "resume-only" | "overwrite";

export interface LineEdit {
  entryId: string;
  key: string;
  line: ResumeLine;
  text: string;
  destination: EditDestination;
}

export interface ResumePreviewProps {
  resume: StructuredResume;
  /**
   * Provide to make the preview EDITABLE. Absent (the default), it renders read-only —
   * which is what the Portfolio page's MASTER résumé preview needs: the master *is* the
   * portfolio, so "apply to this résumé only" is meaningless there and the destination
   * choice is incoherent. Editing is opt-in precisely so it cannot leak into that view.
   */
  onEditLine?: (edit: LineEdit) => Promise<void> | void;
  onEditSummary?: (text: string) => void;
  busyKey?: string | null;
}

function contactLine(r: StructuredResume): string {
  const c = r.contact;
  return [c.email, c.phone, c.location, ...(c.links ?? [])].filter(Boolean).join(" · ");
}

/** Edit one line, then say what the edit MEANS. */
function LineEditor({
  line,
  entryId,
  onSave,
  onCancel,
  busy,
}: {
  line: ResumeLine;
  entryId: string;
  onSave: (edit: LineEdit) => void;
  onCancel: () => void;
  busy: boolean;
}): JSX.Element {
  const [text, setText] = useState(line.text);
  // Defaults to the SAFE destination. Overwrite rewrites the user's portfolio — the thing
  // every future résumé is built from — so it is never preselected and never what the Enter
  // key does. A JD-specific rewording is the common case; permanently changing the master is not.
  const [destination, setDestination] = useState<EditDestination>("resume-only");
  const canPersist = Boolean(line.bullet_id || line.story_id);
  const dirty = text.trim() !== line.text.trim() && text.trim().length > 0;

  return (
    <li className="my-2 list-none rounded-card border border-border bg-surface p-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        maxLength={500}
        aria-label="Edit this line"
        className="w-full rounded-card border border-border bg-card p-2 text-sm text-text"
      />
      {canPersist && (
        <fieldset className="mt-2">
          <legend className="text-xs font-medium text-muted">Apply this change to…</legend>
          <label className="mt-1 flex items-start gap-2 text-sm">
            <input
              type="radio"
              name={`dest-${lineKey(line)}`}
              checked={destination === "resume-only"}
              onChange={() => setDestination("resume-only")}
              className="mt-1"
            />
            <span>
              <span className="text-text">This résumé only</span>
              <span className="block text-xs text-muted">
                Goes in the document you export. Your portfolio is untouched.
              </span>
            </span>
          </label>
          <label className="mt-1 flex items-start gap-2 text-sm">
            <input
              type="radio"
              name={`dest-${lineKey(line)}`}
              checked={destination === "overwrite"}
              onChange={() => setDestination("overwrite")}
              className="mt-1"
            />
            <span>
              <span className="text-text">Replace this line in my portfolio</span>
              <span className="block text-xs text-muted">
                Every future résumé will use this wording. Wording written for one job may not
                suit the next.
              </span>
            </span>
          </label>
        </fieldset>
      )}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={!dirty || busy}
          onClick={() => onSave({ entryId, key: lineKey(line), line, text: text.trim(), destination })}
          className="min-h-tap rounded-card border border-border bg-card px-3 text-sm disabled:opacity-50"
        >
          {busy ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="min-h-tap rounded-card px-3 text-sm text-muted hover:text-text"
        >
          Cancel
        </button>
      </div>
    </li>
  );
}

function Roles({
  roles,
  onEditLine,
  busyKey,
}: {
  roles: RoleBlock[];
  onEditLine?: (edit: LineEdit) => Promise<void> | void;
  busyKey?: string | null;
}): JSX.Element {
  const [editing, setEditing] = useState<string | null>(null);

  return (
    <>
      {roles.map((role) => (
        <div key={role.entry_id || `${role.title}|${role.org}|${role.dates}`} className="mb-3">
          <p className="text-sm font-medium">
            {role.title}
            {role.org ? ` — ${role.org}` : ""}
            {role.dates ? <span className="text-muted"> · {role.dates}</span> : null}
          </p>
          <ul className="ml-4 list-disc text-sm text-muted">
            {(role.bullets ?? []).map((line, j) => {
              const key = lineKey(line) || `new-${j}`;
              if (onEditLine && editing === key) {
                return (
                  <LineEditor
                    key={key}
                    line={line}
                    entryId={role.entry_id ?? ""}
                    busy={busyKey === key}
                    onCancel={() => setEditing(null)}
                    onSave={async (edit) => {
                      await onEditLine(edit);
                      setEditing(null);
                    }}
                  />
                );
              }
              return (
                <li key={key}>
                  {onEditLine ? (
                    <button
                      type="button"
                      onClick={() => setEditing(key)}
                      className="text-left hover:text-text hover:underline"
                      title="Edit this line"
                    >
                      {line.text}
                    </button>
                  ) : (
                    line.text
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </>
  );
}

/**
 * A lightweight React preview of the tailored résumé (§4.5). The exact export
 * bytes still come from the server renderers behind `POST /api/resume/{fmt}`; this
 * is the on-screen approximation.
 *
 * Editing is **opt-in** (`onEditLine`) — see {@link ResumePreviewProps}.
 */
export function ResumePreview({
  resume,
  onEditLine,
  onEditSummary,
  busyKey,
}: ResumePreviewProps): JSX.Element {
  // The generated types mark list fields optional (server defaults them to []).
  const skills = resume.skills ?? [];
  const experience = resume.experience ?? [];
  const education = resume.education ?? [];
  const [editingSummary, setEditingSummary] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState(resume.summary);

  return (
    <div className="rounded-card border border-border bg-card p-5 text-text">
      <h2 className="text-lg font-semibold">{resume.contact.name || "Your résumé"}</h2>
      {contactLine(resume) && (
        <p className="mb-3 text-xs text-muted">{contactLine(resume)}</p>
      )}
      {(resume.summary || editingSummary) && (
        <section className="mb-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Summary</h3>
          {onEditSummary && editingSummary ? (
            <div>
              <textarea
                value={summaryDraft}
                onChange={(e) => setSummaryDraft(e.target.value)}
                rows={3}
                aria-label="Edit the summary"
                className="w-full rounded-card border border-border bg-surface p-2 text-sm"
              />
              <div className="mt-1 flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    onEditSummary(summaryDraft.trim());
                    setEditingSummary(false);
                  }}
                  className="min-h-tap rounded-card border border-border px-3 text-sm"
                >
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSummaryDraft(resume.summary);
                    setEditingSummary(false);
                  }}
                  className="min-h-tap rounded-card px-3 text-sm text-muted hover:text-text"
                >
                  Cancel
                </button>
              </div>
              {/* The summary is written by the model for THIS job and is not part of the
                  portfolio, so an edit here can only ever live in this document. There is no
                  destination to choose. */}
              <p className="mt-1 text-xs text-muted">Applies to this résumé only.</p>
            </div>
          ) : onEditSummary ? (
            <button
              type="button"
              onClick={() => {
                setSummaryDraft(resume.summary);
                setEditingSummary(true);
              }}
              className="text-left text-sm hover:underline"
              title="Edit the summary"
            >
              {resume.summary}
            </button>
          ) : (
            <p className="text-sm">{resume.summary}</p>
          )}
        </section>
      )}
      {skills.length > 0 && (
        <section className="mb-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Skills</h3>
          <p className="text-sm">{skills.join(" · ")}</p>
        </section>
      )}
      {experience.length > 0 && (
        <section className="mb-3">
          <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted">
            Experience
          </h3>
          <Roles roles={experience} onEditLine={onEditLine} busyKey={busyKey} />
        </section>
      )}
      {education.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted">
            Education
          </h3>
          <Roles roles={education} />
        </section>
      )}
    </div>
  );
}
