"use client";

import { useState } from "react";

import { ActionCard } from "@/components/ActionCard";
import { InlineError } from "@/components/InlineError";
import { PrimaryButton } from "@/components/PrimaryButton";
import { ResumePreview } from "@/components/ResumePreview";
import { useTailor, type ExportFormat } from "@/lib/tailor/useTailor";

const FORMATS: { fmt: ExportFormat; label: string }[] = [
  { fmt: "pdf", label: "PDF" },
  { fmt: "docx", label: "Word" },
  { fmt: "md", label: "Markdown" },
];

/**
 * Tailor (§4.5): paste a JD → one model call selects JD-relevant achievements and
 * writes a tailored summary/skills → preview → export (PDF/Word/Markdown). Two-pane
 * on desktop, stacked on mobile.
 */
export function TailorContent(): JSX.Element {
  const tailor = useTailor();
  const [jd, setJd] = useState("");
  const [instructions, setInstructions] = useState("");

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
            <ResumePreview resume={tailor.resume} />
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted">Export:</span>
              {FORMATS.map(({ fmt, label }) => (
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
