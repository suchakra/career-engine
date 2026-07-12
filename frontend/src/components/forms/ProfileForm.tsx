"use client";

import { useEffect, useState } from "react";

import { CollapsibleSection } from "@/components/CollapsibleSection";
import { Field } from "@/components/Field";
import { PrimaryButton } from "@/components/PrimaryButton";
import { useProfile, useSaveProfile } from "@/lib/query/hooks";

/**
 * Minimal résumé-header profile form (progressive disclosure) over a deliberate
 * subset of UserProfile — the save flows through the optimistic-write / rollback
 * data layer (AD-16.8).
 *
 * Two things this form must get right, because the workspace store does a
 * FULL-DOCUMENT write:
 *
 * 1. It HYDRATES from `GET /api/profile`. Without that it mounted empty every visit,
 *    so a persisted profile looked like it had never saved at all.
 * 2. It SPREADS the loaded profile into the submitted body. Posting only the two
 *    fields it edits would let `email` / `phone` / `links` fall back to their server
 *    defaults and silently wipe whatever the résumé parser or Tailor had stored.
 *
 * Save is disabled unless the form is dirty, and is disabled entirely when the host
 * view failed to load (data-loss prevention).
 */
export function ProfileForm({ disabled = false }: { disabled?: boolean }): JSX.Element {
  const { data: profile } = useProfile();
  const save = useSaveProfile();

  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [dirty, setDirty] = useState(false);

  // Hydrate once the persisted profile arrives — but never clobber edits in flight.
  useEffect(() => {
    if (!profile || dirty) return;
    setName(profile.name ?? "");
    setLocation(profile.location ?? "");
    // `dirty` is intentionally read-but-not-tracked: re-running on a dirty flip would
    // overwrite what the user just typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile]);

  const onSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    // Never submit before the profile has loaded: spreading an `undefined` profile would
    // post a partial body, and the store's full-document write would blank the fields
    // this form doesn't edit. Save stays disabled until then (see `hydrated` below), and
    // this guard closes the race for a submit already in flight.
    if (!profile) return;
    // Clear dirty only once the save succeeds — on error the form stays dirty so the
    // user can retry without re-editing (the hook rolls the cache back).
    save.mutate({ ...profile, name, location }, { onSuccess: () => setDirty(false) });
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
          {/* `!profile` also covers a FAILED profile read: saving on top of a profile we
              couldn't load would blank it, so we keep Save disabled — the same
              data-loss-prevention rule the `disabled` prop applies for the host view. */}
          <PrimaryButton
            type="submit"
            disabled={disabled || !dirty || save.isPending || !profile}
          >
            {save.isPending ? "Saving…" : "Save"}
          </PrimaryButton>
        </div>
      </form>
    </CollapsibleSection>
  );
}
