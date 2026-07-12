"use client";

import { useCallback, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import type { StructuredResume } from "@/lib/api/models";
import { downloadResume, FORMAT_LABEL, type ExportFormat } from "@/lib/tailor/resumeExport";

export interface MasterResumeController {
  resume: StructuredResume | null;
  building: boolean;
  exporting: ExportFormat | null;
  error: string | null;
  build: () => Promise<void>;
  exportResume: (fmt: ExportFormat) => Promise<void>;
}

/**
 * Master-résumé controller (§4.4): `POST /api/master-resume` assembles every validated
 * achievement (deterministic — no model call, no BYOK key), then the same
 * `POST /api/resume/{fmt}` renderer exports it as `master-resume.{fmt}`.
 */
export function useMasterResume(): MasterResumeController {
  const [resume, setResume] = useState<StructuredResume | null>(null);
  const [building, setBuilding] = useState(false);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  const build = useCallback(async () => {
    setBuilding(true);
    setError(null);
    try {
      setResume(await apiFetch<StructuredResume>("/api/master-resume", { method: "POST" }));
    } catch {
      setError("Couldn't build your master résumé — try again.");
    } finally {
      setBuilding(false);
    }
  }, []);

  const exportResume = useCallback(
    async (fmt: ExportFormat) => {
      if (!resume) return;
      setExporting(fmt);
      setError(null);
      try {
        await downloadResume(resume, fmt, `master-resume.${fmt}`);
      } catch {
        setError(`Couldn't export ${FORMAT_LABEL[fmt]} — try again.`);
      } finally {
        setExporting(null);
      }
    },
    [resume],
  );

  return { resume, building, exporting, error, build, exportResume };
}
