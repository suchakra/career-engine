"use client";

import { useCallback, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import type { ResumeLine, RoleBlock, StructuredResume, TailorRequest } from "@/lib/api/models";
import { downloadResume, FORMAT_LABEL, type ExportFormat } from "@/lib/tailor/resumeExport";

export type { ExportFormat };

/** Address one line: a bullet-backed line by its bullet, else the story it speaks for. */
export function lineKey(line: ResumeLine): string {
  return line.bullet_id || line.story_id;
}

export interface TailorController {
  resume: StructuredResume | null;
  tailoring: boolean;
  exporting: ExportFormat | null;
  error: string | null;
  tailor: (input: TailorRequest) => Promise<void>;
  exportResume: (fmt: ExportFormat) => Promise<void>;
  /** Rewrite one line's text in the previewed résumé. */
  editLine: (entryId: string, key: string, text: string) => void;
  /** Re-identify a line as the bullet that now backs it (after a story-line overwrite). */
  identifyLine: (entryId: string, key: string, bulletId: string) => void;
  editSummary: (text: string) => void;
  editSkills: (skills: string[]) => void;
}

function mapBlocks(
  blocks: RoleBlock[] | undefined,
  entryId: string,
  key: string,
  fn: (line: ResumeLine) => ResumeLine,
): RoleBlock[] {
  return (blocks ?? []).map((block) =>
    block.entry_id !== entryId
      ? block
      : {
          ...block,
          bullets: (block.bullets ?? []).map((line) =>
            lineKey(line) === key ? fn(line) : line,
          ),
        },
  );
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

  const tailor = useCallback(async (input: TailorRequest) => {
    setTailoring(true);
    setError(null);
    try {
      const result = await apiFetch<StructuredResume>("/api/tailor", {
        method: "POST",
        body: input,
      });
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

  const editLine = useCallback((entryId: string, key: string, text: string) => {
    setResume((prev) =>
      !prev
        ? prev
        : {
            ...prev,
            experience: mapBlocks(prev.experience, entryId, key, (l) => ({ ...l, text })),
            education: mapBlocks(prev.education, entryId, key, (l) => ({ ...l, text })),
          },
    );
  }, []);

  const identifyLine = useCallback((entryId: string, key: string, bulletId: string) => {
    // After overwriting a story-backed line, the server has created a bullet that now IS that
    // line. Without adopting its id the client still thinks the line is story-backed, so the
    // user's NEXT edit tries to create a second bullet for the same story and is rejected —
    // locking them out of fixing a typo they just made.
    setResume((prev) =>
      !prev
        ? prev
        : {
            ...prev,
            experience: mapBlocks(prev.experience, entryId, key, (l) => ({
              ...l,
              bullet_id: bulletId,
            })),
            education: mapBlocks(prev.education, entryId, key, (l) => ({
              ...l,
              bullet_id: bulletId,
            })),
          },
    );
  }, []);

  const editSummary = useCallback((summary: string) => {
    setResume((prev) => (prev ? { ...prev, summary } : prev));
  }, []);

  const editSkills = useCallback((skills: string[]) => {
    setResume((prev) => (prev ? { ...prev, skills } : prev));
  }, []);

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
    editSkills,
  };
}
