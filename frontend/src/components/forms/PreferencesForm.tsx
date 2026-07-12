"use client";

import { useEffect, useState } from "react";

import { CollapsibleSection } from "@/components/CollapsibleSection";
import { Field } from "@/components/Field";
import { PrimaryButton } from "@/components/PrimaryButton";
import { usePreferences, useSavePreferences } from "@/lib/query/hooks";

/** Split a comma-separated field into a trimmed, non-empty list. */
function toList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Minimal discovery-preferences (rubric) form — a subset of SessionPreferences,
 * submitted through the optimistic data layer.
 *
 * Same two rules as {@link ProfileForm}, for the same reason (the workspace store does
 * a FULL-DOCUMENT write): it HYDRATES from `GET /api/preferences` (otherwise a saved
 * rubric looked like it never persisted), and it SPREADS the loaded rubric into the
 * body so the fields this form doesn't edit — `nice_to_haves` — aren't reset to empty
 * on every save.
 */
export function PreferencesForm({ disabled = false }: { disabled?: boolean }): JSX.Element {
  const { data: preferences } = usePreferences();
  const save = useSavePreferences();

  const [targetRoles, setTargetRoles] = useState("");
  const [dealbreakers, setDealbreakers] = useState("");
  const [dirty, setDirty] = useState(false);

  // Hydrate once the persisted rubric arrives — but never clobber edits in flight.
  useEffect(() => {
    if (!preferences || dirty) return;
    setTargetRoles((preferences.target_roles ?? []).join(", "));
    setDealbreakers((preferences.dealbreakers ?? []).join(", "));
    // `dirty` is intentionally read-but-not-tracked: re-running on a dirty flip would
    // overwrite what the user just typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preferences]);

  const onSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    // Never submit before the rubric has loaded: spreading an `undefined` value would
    // post a partial body, and the store's full-document write would reset the fields
    // this form doesn't edit (`nice_to_haves`). Save is disabled until then; this guard
    // closes the race for a submit already in flight.
    if (!preferences) return;
    // Clear dirty only on success so a failed save stays retryable (rollback via the
    // hook keeps the cache consistent; the form keeps the user's input).
    save.mutate(
      {
        ...preferences,
        target_roles: toList(targetRoles),
        dealbreakers: toList(dealbreakers),
      },
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
          {/* `!preferences` also covers a FAILED read: saving on top of a rubric we
              couldn't load would reset it, so Save stays disabled (data-loss
              prevention, same rule as the `disabled` prop). */}
          <PrimaryButton
            type="submit"
            disabled={disabled || !dirty || save.isPending || !preferences}
          >
            {save.isPending ? "Saving…" : "Save"}
          </PrimaryButton>
        </div>
      </form>
    </CollapsibleSection>
  );
}
