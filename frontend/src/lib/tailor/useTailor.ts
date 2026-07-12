"use client";

import { useCallback, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import type { StructuredResume, TailorRequest } from "@/lib/api/models";
import { downloadResume, FORMAT_LABEL, type ExportFormat } from "@/lib/tailor/resumeExport";

export type { ExportFormat };

export interface TailorController {
  resume: StructuredResume | null;
  tailoring: boolean;
  exporting: ExportFormat | null;
  error: string | null;
  tailor: (input: TailorRequest) => Promise<void>;
  exportResume: (fmt: ExportFormat) => Promise<void>;
}

/**
 * Tailor turn controller: `POST /api/tailor` → a `StructuredResume` for preview,
 * then `POST /api/resume/{fmt}` → download the rendered bytes (see
 * {@link downloadResume}, shared with the master résumé).
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

  return { resume, tailoring, exporting, error, tailor, exportResume };
}
