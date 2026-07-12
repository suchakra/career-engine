"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch, apiFetchForm, apiStream } from "@/lib/api/client";
import type {
  GrillActionRequest,
  GrillErrorEvent,
  GrillSnapshot,
  GrillTurnEvent,
} from "@/lib/api/grill";

/** One rendered line of the transcript. */
export interface Transcript {
  role: "assistant" | "user";
  text: string;
}

/** What the client should render next (mirrors the server `awaiting` snapshot). */
export type Awaiting = "idle" | "question" | "checkpoint" | "complete";

export interface GrillController {
  transcript: Transcript[];
  /** The "📌 Currently grilling" banner — always the server's effective label. */
  banner: string;
  awaiting: Awaiting;
  /** True while the SSE stream is open (composer disables, caret shows). */
  streaming: boolean;
  error: GrillErrorEvent | null;
  start: (history: string) => Promise<void>;
  startFromResume: (file: File) => Promise<void>;
  answer: (text: string) => Promise<void>;
  confirm: () => Promise<void>;
}

function awaitingFromTurn(t: GrillTurnEvent): Awaiting {
  if (t.is_complete) return "complete";
  if (t.checkpoint_summary) return "checkpoint";
  return "question";
}

/**
 * The grill turn controller (AD-16.5): POST the caller's input to record it, then
 * consume the SSE stream and append each completed assistant turn.
 *
 * The banner is taken verbatim from the server (`frontier_label` / `GrillSnapshot`)
 * and never re-derived client-side (a hard requirement, per BUG-2). The terminal
 * `done` frame re-emits the last turn, so we append only on `turn` and use `done`
 * purely to settle the banner + await state (no duplicate line).
 */
export function useGrill(): GrillController {
  const [transcript, setTranscript] = useState<Transcript[]>([]);
  const [banner, setBanner] = useState("");
  const [awaiting, setAwaiting] = useState<Awaiting>("idle");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<GrillErrorEvent | null>(null);
  // Abort the in-flight stream on unmount so a navigation-away can't keep the
  // request running or surface a misleading "connection lost".
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  const runStream = useCallback(async () => {
    const controller = new AbortController();
    abortRef.current = controller;
    setStreaming(true);
    setError(null);
    try {
      await apiStream(
        "/api/grill/stream",
        (event, data) => {
          if (event === "error") {
            setError(JSON.parse(data) as GrillErrorEvent);
            return;
          }
          const turn = JSON.parse(data) as GrillTurnEvent;
          setBanner(turn.frontier_label);
          setAwaiting(awaitingFromTurn(turn));
          if (event === "turn") {
            const text = turn.checkpoint_summary || turn.next_question;
            if (text) setTranscript((prev) => [...prev, { role: "assistant", text }]);
          }
        },
        { signal: controller.signal },
      );
    } catch {
      // Aborted (unmount) → not an error to surface. Otherwise the stream dropped
      // (network / 5xx): preserve the partial transcript; the durable session means
      // a reload resumes with no lost work.
      if (!controller.signal.aborted) {
        setError({
          message: "Connection lost — reload to resume where you left off.",
          rate_limited: false,
        });
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      if (!controller.signal.aborted) setStreaming(false);
    }
  }, []);

  const post = useCallback(
    async (body: GrillActionRequest) => {
      const snap = await apiFetch<GrillSnapshot>("/api/grill", { method: "POST", body });
      setBanner(snap.frontier_label);
      // Settle the await state from the snapshot before the stream opens (e.g. hide
      // the checkpoint card immediately after confirm) — don't wait for the first frame.
      setAwaiting(snap.awaiting);
      await runStream();
    },
    [runStream],
  );

  const start = useCallback(
    (history: string) => {
      setTranscript([{ role: "user", text: history }]);
      return post({ action: "start", history, answer: "", reference_date: "" });
    },
    [post],
  );

  const startFromResume = useCallback(
    async (file: File) => {
      setTranscript([{ role: "user", text: `📎 Uploaded résumé: ${file.name}` }]);
      setError(null);
      // Parsing is a slow VISION call on the user's key (many seconds). `streaming` is
      // what drives the transcript's progress caret, and it was only being set inside
      // runStream() — so for the whole parse the screen sat dead on the upload bubble
      // with no indication anything was happening. Flip it now, before the request.
      setStreaming(true);
      const form = new FormData();
      form.append("file", file);
      try {
        const snap = await apiFetchForm<GrillSnapshot>("/api/grill/resume", form);
        setBanner(snap.frontier_label);
        setAwaiting(snap.awaiting);
        // runStream owns `streaming` from here (it sets it true, then false when done).
        await runStream();
      } catch {
        setStreaming(false);
        setError({
          message: "Couldn't read that résumé — try another file or paste your history.",
          rate_limited: false,
        });
      }
    },
    [runStream],
  );

  const answer = useCallback(
    (text: string) => {
      setTranscript((prev) => [...prev, { role: "user", text }]);
      return post({ action: "answer", answer: text, history: "", reference_date: "" });
    },
    [post],
  );

  const confirm = useCallback(
    () => post({ action: "confirm", answer: "", history: "", reference_date: "" }),
    [post],
  );

  return { transcript, banner, awaiting, streaming, error, start, startFromResume, answer, confirm };
}
