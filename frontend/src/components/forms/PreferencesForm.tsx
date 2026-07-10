"use client";

import { useState } from "react";

import { CollapsibleSection } from "@/components/CollapsibleSection";
import { Field } from "@/components/Field";
import { PrimaryButton } from "@/components/PrimaryButton";
import { useSavePreferences } from "@/lib/query/hooks";

/** Split a comma-separated field into a trimmed, non-empty list. */
function toList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Minimal discovery-preferences (rubric) form. Subset of SessionPreferences for
 * 10.5; submit posts a schema-valid body through the optimistic data layer.
 */
export function PreferencesForm({ disabled = false }: { disabled?: boolean }): JSX.Element {
  const [targetRoles, setTargetRoles] = useState("");
  const [dealbreakers, setDealbreakers] = useState("");
  const [dirty, setDirty] = useState(false);
  const save = useSavePreferences();

  const onSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    // Clear dirty only on success so a failed save stays retryable (rollback via
    // the hook keeps the cache consistent; the form keeps the user's input).
    save.mutate(
      { target_roles: toList(targetRoles), dealbreakers: toList(dealbreakers) },
      { onSuccess: () => setDirty(false) },
    );
  };

  return (
    <CollapsibleSection title="Job preferences">
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <Field
          label="Target roles"
          hint="Comma-separated (e.g. Staff Engineer, Eng Manager)"
          value={targetRoles}
          disabled={disabled}
          onChange={(e) => {
            setTargetRoles(e.target.value);
            setDirty(true);
          }}
        />
        <Field
          label="Dealbreakers"
          hint="Comma-separated absolute exclusions (e.g. on-site, no cloud)"
          value={dealbreakers}
          disabled={disabled}
          onChange={(e) => {
            setDealbreakers(e.target.value);
            setDirty(true);
          }}
        />
        <div>
          <PrimaryButton type="submit" disabled={disabled || !dirty || save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </PrimaryButton>
        </div>
      </form>
    </CollapsibleSection>
  );
}
