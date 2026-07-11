"use client";

import { useState } from "react";

import { ActionCard } from "@/components/ActionCard";
import { PrimaryButton } from "@/components/PrimaryButton";
import { StatusBadge } from "@/components/StatusBadge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useKeyStatus, useRemoveKey, useSaveKey } from "@/lib/query/hooks";

/** Settings (§4.6) — BYOK key management + appearance. */
export function SettingsContent(): JSX.Element {
  const status = useKeyStatus();
  const save = useSaveKey();
  const remove = useRemoveKey();
  const [key, setKey] = useState("");
  const hasKey = status.data?.has_key ?? false;

  const onSave = (): void => {
    const k = key.trim();
    if (!k) return;
    save.mutate(k, { onSuccess: () => setKey("") });
  };

  return (
    <div className="flex flex-col gap-6">
      <ActionCard title="API key (BYOK)">
        <p className="mb-3 text-sm text-muted">
          Grill and tailor run on <strong>your own</strong> Gemini key. Stored encrypted in
          Secret Manager — never in our database or logs, and never shown again after saving.
        </p>
        <div className="mb-3">
          {status.isLoading ? (
            <span className="text-sm text-muted">Checking…</span>
          ) : hasKey ? (
            <StatusBadge status="strong" label="Using your saved key" />
          ) : (
            <StatusBadge status="skipped" label="No key yet" />
          )}
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="apikey" className="text-sm font-medium">
              {hasKey ? "Change key" : "Set your Gemini key"}
            </label>
            <input
              id="apikey"
              type="password"
              autoComplete="off"
              value={key}
              placeholder="AIza…"
              aria-label="Gemini API key"
              onChange={(e) => setKey(e.target.value)}
              className="min-h-tap w-72 max-w-full rounded-card border border-border bg-surface px-3 text-sm text-text placeholder:text-muted"
            />
          </div>
          <PrimaryButton onClick={onSave} disabled={!key.trim() || save.isPending}>
            {save.isPending ? "Saving…" : "Save & use this key"}
          </PrimaryButton>
          {hasKey && (
            <PrimaryButton
              variant="secondary"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
            >
              Remove key
            </PrimaryButton>
          )}
        </div>
        <p className="mt-2 text-xs text-muted">
          Get a key at{" "}
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

      <ActionCard title="Appearance">
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted">Theme</span>
          <ThemeToggle />
        </div>
      </ActionCard>
    </div>
  );
}
