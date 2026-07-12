"use client";

import { useState } from "react";

import { ActionCard } from "@/components/ActionCard";
import { InlineError } from "@/components/InlineError";
import { PrimaryButton } from "@/components/PrimaryButton";
import { StreamingTranscript } from "@/components/StreamingTranscript";
import { useGrill } from "@/lib/grill/useGrill";

/**
 * The interactive grill (§4.3) over the 10.4 SSE endpoint. First-run seeds the
 * session from pasted history; thereafter answers stream turn-by-turn. The
 * "currently grilling" banner is always the server's effective label (never
 * re-derived client-side, per BUG-2).
 */
export function GrillContent(): JSX.Element {
  const grill = useGrill();
  const [history, setHistory] = useState("");
  // Branch on the SERVER's answer, not on in-memory state. Deciding this client-side
  // (`awaiting === "idle" && transcript.length === 0`) meant every fresh page load
  // showed the start card — even on top of a live session, and even right after the
  // user clicked "Grill me about this" in the Portfolio.
  const notStarted = grill.hasSession === false;

  // A failed status read must NOT fall through to the start card: starting a grill
  // creates the session (last-write-wins), so offering it here would let a transient
  // read error destroy a portfolio we merely failed to load.
  if (grill.statusFailed) {
    return (
      <InlineError message="Couldn't load your grill — reload the page to try again. Your work is safe." />
    );
  }

  if (grill.hasSession === null) {
    return <p className="text-sm text-muted">Loading your grill…</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {grill.banner && (
        <p className="text-sm font-medium">
          <span aria-hidden="true">📌 </span>
          Currently grilling: {grill.banner}
        </p>
      )}

      {notStarted ? (
        <ActionCard title="Start grilling">
          <div className="mb-4">
            <label htmlFor="resume" className="text-sm font-medium">
              Drop your résumé <span className="text-muted">(PDF, PNG, JPG — parsed on your key)</span>
            </label>
            <input
              id="resume"
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/*"
              aria-label="Résumé file"
              // The file:* button needs its OWN text colour — without file:text-text it
              // falls back to the UA default (near-black) and vanishes on the dark surface.
              className="mt-1 block w-full text-sm text-muted file:mr-3 file:min-h-tap file:cursor-pointer file:rounded-card file:border file:border-border file:bg-surface file:px-3 file:text-sm file:font-medium file:text-text hover:file:bg-card"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void grill.startFromResume(f);
              }}
            />
          </div>
          <p className="mb-3 text-sm text-muted">
            …or paste your career history and start:
          </p>
          <textarea
            className="mb-3 min-h-[8rem] w-full resize-y rounded-card border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-muted"
            value={history}
            placeholder="I led the platform team at Acme from 2019–2024…"
            aria-label="Career history"
            onChange={(e) => setHistory(e.target.value)}
          />
          <PrimaryButton
            onClick={() => void grill.start(history)}
            disabled={!history.trim() || grill.streaming}
          >
            ▸ Start grilling
          </PrimaryButton>
        </ActionCard>
      ) : (
        <StreamingTranscript
          turns={grill.transcript}
          streaming={grill.streaming}
          onSubmit={(text) => void grill.answer(text)}
          composerHidden={grill.awaiting !== "question"}
        />
      )}

      {grill.awaiting === "checkpoint" && (
        <ActionCard title="Checkpoint reached">
          <p className="mb-3 text-sm text-muted">
            Stories saved and visible in Portfolio. Confirm to keep going.
          </p>
          <PrimaryButton
            onClick={() => void grill.confirm()}
            disabled={grill.streaming}
          >
            Looks right — keep going
          </PrimaryButton>
        </ActionCard>
      )}

      {grill.awaiting === "complete" && (
        <ActionCard title="Grill complete 🎉">
          <p className="mb-3 text-sm text-muted">
            Your portfolio is updated. Build a tailored résumé next.
          </p>
          <PrimaryButton asChild>
            <a href="/tailor">Tailor a résumé →</a>
          </PrimaryButton>
        </ActionCard>
      )}

      {grill.error && (
        <InlineError
          message={
            grill.error.rate_limited
              ? `${grill.error.message} (rate limited — try again shortly)`
              : grill.error.message
          }
        />
      )}
    </div>
  );
}
