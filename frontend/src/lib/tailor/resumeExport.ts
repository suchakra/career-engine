"use client";

import { apiFetchBlob } from "@/lib/api/client";
import type { StructuredResume } from "@/lib/api/models";

export type ExportFormat = "pdf" | "docx" | "md";

/** User-facing labels (avoid showing raw "MD"). The single source of truth. */
export const FORMAT_LABEL: Record<ExportFormat, string> = {
  pdf: "PDF",
  docx: "Word",
  md: "Markdown",
};

/** The export buttons to render, derived from {@link FORMAT_LABEL} so they can't drift. */
export const EXPORT_FORMATS: { fmt: ExportFormat; label: string }[] = (
  Object.keys(FORMAT_LABEL) as ExportFormat[]
).map((fmt) => ({ fmt, label: FORMAT_LABEL[fmt] }));

/** Trigger a browser download of a blob (separated so the fetch stays testable). */
function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoke on a later tick so the download has started (revoking synchronously can
  // invalidate the blob URL before the browser reads it).
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/**
 * Render a résumé server-side and download the bytes. Export is a stateless POST-render
 * RPC (the résumé the server returned is passed back), matching `POST /api/resume/{fmt}`.
 * Shared by the tailored résumé (§4.5) and the master résumé (§4.4).
 */
export async function downloadResume(
  resume: StructuredResume,
  fmt: ExportFormat,
  filename = `resume.${fmt}`,
): Promise<void> {
  const blob = await apiFetchBlob(`/api/resume/${fmt}`, { method: "POST", body: resume });
  triggerDownload(blob, filename);
}
