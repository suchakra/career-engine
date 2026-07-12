"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiFetch } from "@/lib/api/client";
import type {
  Application,
  ApplicationWriteRequest,
  DashboardResponse,
  JobsResponse,
  MeResponse,
  PortfolioResponse,
  SessionPreferences,
  UserProfile,
} from "@/lib/api/models";
import { queryKeys } from "@/lib/query/keys";
import { useToast } from "@/components/Toast";

// ── Read hooks (keys mirror the read APIs) ───────────────────────────────────

export function useMe(): UseQueryResult<MeResponse> {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: () => apiFetch<MeResponse>("/api/me"),
  });
}

export function useDashboard(): UseQueryResult<DashboardResponse> {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: () => apiFetch<DashboardResponse>("/api/dashboard"),
  });
}

export function usePortfolio(): UseQueryResult<PortfolioResponse> {
  return useQuery({
    queryKey: queryKeys.portfolio,
    queryFn: () => apiFetch<PortfolioResponse>("/api/portfolio"),
  });
}

export function useJobs(): UseQueryResult<JobsResponse> {
  return useQuery({
    queryKey: queryKeys.jobs,
    queryFn: () => apiFetch<JobsResponse>("/api/jobs"),
  });
}

/**
 * The persisted profile. Without this the Profile form had nothing to hydrate from:
 * it mounted empty on every visit, so a saved profile looked like it never persisted.
 */
export function useProfile(): UseQueryResult<UserProfile> {
  return useQuery({
    queryKey: queryKeys.profile,
    queryFn: () => apiFetch<UserProfile>("/api/profile"),
  });
}

/** The persisted discovery rubric (same hydration story as {@link useProfile}). */
export function usePreferences(): UseQueryResult<SessionPreferences> {
  return useQuery({
    queryKey: queryKeys.preferences,
    queryFn: () => apiFetch<SessionPreferences>("/api/preferences"),
  });
}

// ── Mutation hooks (optimistic write → rollback → invalidate) ─────────────────

/**
 * Form inputs are a Partial of the domain model: every field has a server-side
 * default, so a minimal body is valid (the server fills the rest, incl.
 * contract_version). This avoids hardcoding a contract version in the client.
 */
export type SaveProfileInput = Partial<UserProfile>;
export type SavePreferencesInput = Partial<SessionPreferences>;

interface OptimisticContext<T> {
  previous: T | undefined;
}

/**
 * Save the résumé-header profile with an optimistic cache update.
 *
 * onMutate: cancel in-flight `me`/`dashboard`-adjacent queries and snapshot +
 * patch the profile cache. onError: roll back to the snapshot and surface a Toast.
 * onSettled: invalidate so the server value reconciles (AD-16.8).
 */
export function useSaveProfile(): UseMutationResult<
  UserProfile,
  unknown,
  SaveProfileInput,
  OptimisticContext<SaveProfileInput>
> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const key = queryKeys.profile;

  return useMutation({
    mutationFn: (profile: SaveProfileInput) =>
      apiFetch<UserProfile>("/api/profile", { method: "POST", body: profile }),
    onMutate: async (profile) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<SaveProfileInput>(key);
      queryClient.setQueryData<SaveProfileInput>(key, profile);
      return { previous };
    },
    onError: (_err, _profile, context) => {
      if (context) {
        queryClient.setQueryData(key, context.previous);
      }
      showToast("Couldn't save your profile — changes were reverted.", "error");
    },
    onSuccess: () => {
      showToast("Profile saved.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: key });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

/**
 * Save the discovery preferences (rubric) with an optimistic cache update.
 * Same optimistic → rollback → invalidate shape as {@link useSaveProfile}.
 */
export function useSavePreferences(): UseMutationResult<
  SessionPreferences,
  unknown,
  SavePreferencesInput,
  OptimisticContext<SavePreferencesInput>
> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const key = queryKeys.preferences;

  return useMutation({
    mutationFn: (prefs: SavePreferencesInput) =>
      apiFetch<SessionPreferences>("/api/preferences", { method: "PUT", body: prefs }),
    onMutate: async (prefs) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<SavePreferencesInput>(key);
      queryClient.setQueryData<SavePreferencesInput>(key, prefs);
      return { previous };
    },
    onError: (_err, _prefs, context) => {
      if (context) {
        queryClient.setQueryData(key, context.previous);
      }
      showToast("Couldn't save your preferences — changes were reverted.", "error");
    },
    onSuccess: () => {
      showToast("Preferences saved.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: key });
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
    },
  });
}

// ── BYOK key management (parity P1) ───────────────────────────────────────────

export interface KeyStatus {
  has_key: boolean;
}

/** Whether the caller has a saved Gemini key (drives the key chip + gates). */
export function useKeyStatus(): UseQueryResult<KeyStatus> {
  return useQuery({
    queryKey: queryKeys.key,
    queryFn: () => apiFetch<KeyStatus>("/api/key"),
  });
}

/** Save the user's Gemini key (BYOK) → Secret Manager. Never echoed back. */
export function useSaveKey(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (apiKey: string) =>
      apiFetch<void>("/api/key", { method: "POST", body: { api_key: apiKey } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.key });
      showToast("Key saved — grill and tailor are ready.", "success");
    },
    onError: () => showToast("Couldn't save your key — try again.", "error"),
  });
}

/** Remove the user's saved key. */
export function useRemoveKey(): UseMutationResult<void, unknown, void> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () => apiFetch<void>("/api/key", { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.key });
      showToast("Key removed.", "info");
    },
    onError: () => showToast("Couldn't remove your key — try again.", "error"),
  });
}

// ── Jobs discovery run (parity P2) ────────────────────────────────────────────

/** Run job discovery (BYOK) → fresh JobsView; updates the jobs cache in place. */
export function useDiscoverJobs(): UseMutationResult<JobsResponse, unknown, void> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () => apiFetch<JobsResponse>("/api/jobs/discover", { method: "POST" }),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.jobs, data);
      showToast(
        `Found ${data.accepted.length} strong · ${data.for_review.length} for review.`,
        "success",
      );
    },
    onError: (err) => {
      const status = (err as { status?: number }).status;
      showToast(
        status === 409
          ? "Add your Gemini key in Settings first, then search."
          : "Job search failed — try again.",
        "error",
      );
    },
  });
}

// ── Track application (parity P4) ─────────────────────────────────────────────

/** Save a tailored résumé as a tracked application (POST /api/applications). */
export function useTrackApplication(): UseMutationResult<
  Application,
  unknown,
  ApplicationWriteRequest
> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (input: ApplicationWriteRequest) =>
      apiFetch<Application>("/api/applications", { method: "POST", body: input }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      showToast("Saved to your tracked applications.", "success");
    },
    onError: () => showToast("Couldn't save the application — try again.", "error"),
  });
}

// ── Portfolio actions (parity P4b) ─────────────────────────────────────────────

/**
 * Pin the grill onto a chosen entry (§4.4 "Grill me about this"). On success the
 * grill frontier is set server-side; we route the user to /grill to continue.
 */
export function useGrillEntry(): UseMutationResult<void, unknown, string> {
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (entryId: string) =>
      apiFetch<void>(`/api/experience/${entryId}/grill`, { method: "POST" }),
    onError: () => showToast("Couldn't start a grill on that entry.", "error"),
  });
}

/** Pin/unpin an entry so it is always tailored (§4.4). Refreshes the portfolio. */
export function useHighlightEntry(): UseMutationResult<
  void,
  unknown,
  { entryId: string; highlighted: boolean }
> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: ({ entryId, highlighted }) =>
      apiFetch<void>(`/api/experience/${entryId}/highlight`, {
        method: "POST",
        body: { highlighted },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio });
    },
    onError: () => showToast("Couldn't update that entry — try again.", "error"),
  });
}

/** Append a new bullet to an experience — add a line without re-grilling the entry. */
export function useAddBullet(): UseMutationResult<
  void,
  unknown,
  { entryId: string; text: string }
> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: ({ entryId, text }) =>
      apiFetch<void>(`/api/experience/${entryId}/bullet`, {
        method: "POST",
        body: { text },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio });
      showToast("Bullet added.", "success");
    },
    onError: () => showToast("Couldn't add that bullet — try again.", "error"),
  });
}

/** Delete one bullet from an experience (CQ-3). Refreshes the portfolio. */
export function useDeleteBullet(): UseMutationResult<
  void,
  unknown,
  { entryId: string; bulletId: string }
> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: ({ entryId, bulletId }) =>
      apiFetch<void>(`/api/experience/${entryId}/bullet/${bulletId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio });
      showToast("Bullet deleted.", "success");
    },
    onError: () => showToast("Couldn't delete that bullet — try again.", "error"),
  });
}

/**
 * Delete a whole experience (CQ-3). The server CASCADES to its STAR stories, so this
 * also removes the grilled work attached to that role — hence the confirm in the UI.
 */
export function useDeleteEntry(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (entryId: string) =>
      apiFetch<void>(`/api/experience/${entryId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      showToast("Experience deleted.", "success");
    },
    onError: () => showToast("Couldn't delete that experience — try again.", "error"),
  });
}

/** Edit one bullet on an experience in place (parity P5). Refreshes the portfolio. */
export function useEditBullet(): UseMutationResult<
  void,
  unknown,
  { entryId: string; bulletId: string; newText: string }
> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: ({ entryId, bulletId, newText }) =>
      apiFetch<void>(`/api/experience/${entryId}/bullet`, {
        method: "PATCH",
        body: { bullet_id: bulletId, new_text: newText },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio });
      showToast("Bullet updated.", "success");
    },
    onError: () => showToast("Couldn't update that bullet — try again.", "error"),
  });
}

/**
 * Dismiss a company ("Not interested", parity P5): future discovery runs hard-reject it.
 * Refreshes the jobs list, which already filters out dismissed companies server-side.
 */
export function useDismissCompany(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (company: string) =>
      apiFetch<void>("/api/jobs/dismiss", { method: "POST", body: { company } }),
    onSuccess: (_data, company) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      showToast(`${company} won't be suggested again.`, "success");
    },
    onError: () => showToast("Couldn't dismiss that company — try again.", "error"),
  });
}

/** Delete a STAR story (§4.4). Refreshes the portfolio on success. */
export function useDeleteStory(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (storyId: string) =>
      apiFetch<void>(`/api/story/${storyId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio });
      showToast("Story deleted.", "success");
    },
    onError: () => showToast("Couldn't delete that story — try again.", "error"),
  });
}
