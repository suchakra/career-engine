"use client";

import { useState } from "react";

import { PrimaryButton } from "@/components/PrimaryButton";
import { cn } from "@/lib/utils";
import type { Transcript } from "@/lib/grill/useGrill";

export interface StreamingTranscriptProps {
  turns: Transcript[];
  /** True while a turn is streaming — shows the caret, disables the composer. */
  streaming: boolean;
  /** Submit the composed answer (the turn controller is injected by the caller). */
  onSubmit: (text: string) => void;
  /** Hide/disable the composer (e.g. at a checkpoint or on completion). */
  composerHidden?: boolean;
  placeholder?: string;
}

/**
 * Transcript render + SSE streaming surface + composer (§4.3 / §9). The turn
 * controller is injected via `onSubmit` so interview-prep / negotiator can reuse
 * this same surface with different turn logic. Streamed assistant turns settle into
 * an `aria-live="polite"` region (announced per settled turn, not per token).
 */
export function StreamingTranscript({
  turns,
  streaming,
  onSubmit,
  composerHidden = false,
  placeholder = "Your answer…",
}: StreamingTranscriptProps): JSX.Element {
  const [draft, setDraft] = useState("");

  const submit = (): void => {
    const text = draft.trim();
    if (!text || streaming) return;
    onSubmit(text);
    setDraft("");
  };

  return (
    <div className="flex flex-col gap-3">
      <div
        className="flex max-h-[52vh] flex-col gap-3 overflow-y-auto rounded-card border border-border bg-card p-4"
        aria-live="polite"
        aria-atomic="false"
      >
        {turns.length === 0 && !streaming ? (
          <p className="text-sm text-muted">The transcript will appear here.</p>
        ) : (
          turns.map((turn, i) => (
            <div
              key={i}
              className={cn(
                "flex gap-2 text-sm",
                turn.role === "user" && "flex-row-reverse text-right",
              )}
            >
              <span aria-hidden="true">{turn.role === "assistant" ? "🤖" : "🙂"}</span>
              <p
                className={cn(
                  "max-w-[42ch] whitespace-pre-wrap rounded-card px-3 py-2",
                  turn.role === "assistant" ? "bg-surface" : "bg-primary/10",
                )}
              >
                {turn.text}
              </p>
            </div>
          ))
        )}
        {streaming && (
          <p className="text-sm text-muted" role="status">
            <span aria-hidden="true">▍</span> CareerEngine is typing…
          </p>
        )}
      </div>

      {!composerHidden && (
        <div className="flex items-end gap-2">
          <textarea
            className="min-h-tap flex-1 resize-y rounded-card border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-muted"
            rows={2}
            value={draft}
            placeholder={placeholder}
            disabled={streaming}
            aria-label="Your answer"
            onChange={(e) => setDraft(e.target.value)}
          />
          <PrimaryButton onClick={submit} disabled={streaming || !draft.trim()}>
            ▸ Send
          </PrimaryButton>
        </div>
      )}
    </div>
  );
}
