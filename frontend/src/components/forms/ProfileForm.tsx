"use client";

import { useState } from "react";

import { CollapsibleSection } from "@/components/CollapsibleSection";
import { Field } from "@/components/Field";
import { PrimaryButton } from "@/components/PrimaryButton";
import { useSaveProfile } from "@/lib/query/hooks";

/**
 * Minimal résumé-header profile form (progressive disclosure). A deliberate
 * subset of UserProfile for 10.5 — the submit posts a schema-valid body and the
 * save flows through the optimistic-write / rollback data layer (AD-16.8).
 *
 * Save is disabled unless the form is dirty AND is disabled entirely when the
 * host view failed to load (data-loss prevention).
 */
export function ProfileForm({ disabled = false }: { disabled?: boolean }): JSX.Element {
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [dirty, setDirty] = useState(false);
  const save = useSaveProfile();

  const onSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    // Clear dirty only once the save succeeds — on error the form stays dirty so
    // the user can retry without re-editing (the hook rolls the cache back).
    save.mutate({ name, location }, { onSuccess: () => setDirty(false) });
  };

  return (
    <CollapsibleSection
      title="Profile"
      defaultOpen
      headerRight={<span className="text-xs text-muted">(edit)</span>}
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <Field
          label="Full name"
          value={name}
          placeholder="Jane Doe"
          disabled={disabled}
          onChange={(e) => {
            setName(e.target.value);
            setDirty(true);
          }}
        />
        <Field
          label="Location"
          value={location}
          placeholder="Remote · US"
          disabled={disabled}
          onChange={(e) => {
            setLocation(e.target.value);
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
