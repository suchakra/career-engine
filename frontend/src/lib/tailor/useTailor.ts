"use client";

import { useCallback, useState } from "react";

import { apiFetch, apiFetchBlob } from "@/lib/api/client";
import type { StructuredResume, TailorRequest } from "@/lib/api/models";

export type ExportFormat = "pdf" | "docx" | "md";

/** Trigger a browser download of a blob (separated so the fetch stays testable). */
function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

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
 * then `POST /api/resume/{fmt}` → download the rendered bytes. Export is a stateless
 * POST-render RPC (the resume the server returned is passed back), matching the API.
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
        const blob = await apiFetchBlob(`/api/resume/${fmt}`, { method: "POST", body: resume });
        triggerDownload(blob, `resume.${fmt}`);
      } catch {
        setError(`Couldn't export ${fmt.toUpperCase()} — try again.`);
      } finally {
        setExporting(null);
      }
    },
    [resume],
  );

  return { resume, tailoring, exporting, error, tailor, exportResume };
}
