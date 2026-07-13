"use client";

import { useCallback, useRef, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import type { ResumeLine, RoleBlock, StructuredResume, TailorRequest } from "@/lib/api/models";
import { downloadResume, FORMAT_LABEL, type ExportFormat } from "@/lib/tailor/resumeExport";

export type { ExportFormat };

/**
 * A line's address, stable for the life of one tailored preview.
 *
 * **Deliberately positional, not identity-based.** The obvious key — `bullet_id || story_id` —
 * CHANGES the moment a story-backed line is overwritten and adopts the new bullet's id. Every
 * map keyed on it (the undo record, the "which line is saving" flag) would then silently stop
 * matching that line: undo would fail to roll the preview back, the line would keep pointing at
 * a bullet that had just been deleted, and every later overwrite of it would be a no-op that
 * still reported success. Tailoring never inserts or removes lines, so position is stable where
 * identity is not.
 */
export function lineKey(entryId: string, index: number): string {
  return `${entryId}#${index}`;
}

export interface TailorController {
  resume: StructuredResume | null;
  tailoring: boolean;
  exporting: ExportFormat | null;
  error: string | null;
  tailor: (input: TailorRequest) => Promise<void>;
  exportResume: (fmt: ExportFormat) => Promise<void>;
  /** Rewrite one line's text in the previewed résumé. */
  editLine: (key: string, text: string) => void;
  /** Adopt (or, on undo, give back) the bullet that backs a line. */
  identifyLine: (key: string, bulletId: string) => void;
  editSummary: (text: string) => void;
  /**
   * The text a line had when the server tailored it — i.e. what the PORTFOLIO says.
   *
   * Undoing a destructive overwrite must restore THIS, never the current preview text: the
   * preview is mutated by "this résumé only" edits, which the user explicitly chose NOT to
   * persist. Undoing to the preview would write a JD-specific wording into the master résumé
   * that they never agreed to — an undo that leaves things worse than not undoing at all.
   */
  originalText: (key: string) => string;
}

function mapLines(
  blocks: RoleBlock[] | undefined,
  key: string,
  fn: (line: ResumeLine) => ResumeLine,
): RoleBlock[] {
  return (blocks ?? []).map((block) => ({
    ...block,
    bullets: (block.bullets ?? []).map((line, i) =>
      lineKey(block.entry_id ?? "", i) === key ? fn(line) : line,
    ),
  }));
}

/** Snapshot every line's server-truth text, keyed by its stable address. */
function snapshot(resume: StructuredResume): Map<string, string> {
  const originals = new Map<string, string>();
  for (const block of [...(resume.experience ?? []), ...(resume.education ?? [])]) {
    (block.bullets ?? []).forEach((line, i) => {
      originals.set(lineKey(block.entry_id ?? "", i), line.text);
    });
  }
  return originals;
}

/**
 * Tailor turn controller: `POST /api/tailor` → a `StructuredResume` for preview,
 * then `POST /api/resume/{fmt}` → download the rendered bytes (see
 * {@link downloadResume}, shared with the master résumé).
 *
 * **The previewed résumé lives HERE, and edits mutate it here** (CQ-6b). That is not a
 * stylistic choice: `exportResume` and the page's "track as application" both serialize this
 * object. If an edit lived in the preview component's own state, the user would edit a line,
 * watch it change on screen, click PDF — and download the résumé WITHOUT their edit, silently.
 * One object, so the preview, the export and the saved application cannot disagree.
 */
export function useTailor(): TailorController {
  const [resume, setResume] = useState<StructuredResume | null>(null);
  const [tailoring, setTailoring] = useState(false);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A ref, not state: nothing renders from it, and undo must read the CURRENT snapshot rather
  // than one captured in a stale closure.
  const originals = useRef<Map<string, string>>(new Map());

  const tailor = useCallback(async (input: TailorRequest) => {
    setTailoring(true);
    setError(null);
    try {
      const result = await apiFetch<StructuredResume>("/api/tailor", {
        method: "POST",
        body: input,
      });
      originals.current = snapshot(result);
      setResume(result);
    } catch {
      setError("Couldn't tailor your résumé — check your key and try again.");
    } finally {
      setTailoring(false);
    }
  }, []);

  const exportResume = useCallback(
    async (fmt: ExportFormat) => {
      if (!resume) return;
      setExporting(fmt);
      setError(null);
      try {
        await downloadResume(resume, fmt);
      } catch {
        setError(`Couldn't export ${FORMAT_LABEL[fmt]} — try again.`);
      } finally {
        setExporting(null);
      }
    },
    [resume],
  );

  const editLine = useCallback((key: string, text: string) => {
    setResume((prev) =>
      !prev
        ? prev
        : {
            ...prev,
            experience: mapLines(prev.experience, key, (l) => ({ ...l, text })),
            education: mapLines(prev.education, key, (l) => ({ ...l, text })),
          },
    );
  }, []);

  const identifyLine = useCallback((key: string, bulletId: string) => {
    // After overwriting a story-backed line, the server created a bullet that now IS that line;
    // the client must adopt its id, or the next edit would try to create a SECOND bullet for
    // the same story and be refused. Undo passes "" to hand the id back, so the line stops
    // claiming a bullet that no longer exists.
    setResume((prev) =>
      !prev
        ? prev
        : {
            ...prev,
            experience: mapLines(prev.experience, key, (l) => ({ ...l, bullet_id: bulletId })),
            education: mapLines(prev.education, key, (l) => ({ ...l, bullet_id: bulletId })),
          },
    );
  }, []);

  const editSummary = useCallback((summary: string) => {
    setResume((prev) => (prev ? { ...prev, summary } : prev));
  }, []);

  const originalText = useCallback((key: string) => originals.current.get(key) ?? "", []);

  return {
    resume,
    tailoring,
    exporting,
    error,
    tailor,
    exportResume,
    editLine,
    identifyLine,
    editSummary,
    originalText,
  };
}
