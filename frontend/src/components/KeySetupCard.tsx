"use client";

import { useState } from "react";

import { ActionCard } from "@/components/ActionCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { useSaveKey } from "@/lib/query/hooks";

/**
 * Compact BYOK key setup shown on first run (no key resolved) — collapses the
 * first-time path to login → Dashboard key card → start (§4.1 pre-flight key card).
 */
export function KeySetupCard(): JSX.Element {
  const save = useSaveKey();
  const [key, setKey] = useState("");
  const onSave = (): void => {
    const k = key.trim();
    if (k) save.mutate(k, { onSuccess: () => setKey("") });
  };
  return (
    <ActionCard title="Set up your Gemini key (≈30s) to start">
      <p className="mb-3 text-sm text-muted">
        Grill, tailor, and job search run on your own Gemini key — stored encrypted in
        Secret Manager, never in our database or logs.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <input
          type="password"
          autoComplete="off"
          value={key}
          placeholder="AIza…"
          aria-label="Gemini API key"
          onChange={(e) => setKey(e.target.value)}
          className="min-h-tap w-64 max-w-full rounded-card border border-border bg-surface px-3 text-sm text-text placeholder:text-muted"
        />
        <PrimaryButton onClick={onSave} disabled={!key.trim() || save.isPending}>
          {save.isPending ? "Saving…" : "Save & use this key"}
        </PrimaryButton>
      </div>
      <p className="mt-2 text-xs text-muted">
        Get one at{" "}
        <a
          href="https://aistudio.google.com/apikey"
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-text"
        >
          aistudio.google.com/apikey
        </a>
        .
      </p>
    </ActionCard>
  );
}
