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
  const key = ["profile"] as const;

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
  const key = ["preferences"] as const;

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
