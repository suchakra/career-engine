/**
 * Query keys mirror the read API resources (AD-16.8). Kept in one place so read
 * hooks and mutation invalidations reference the same identity.
 */
export const queryKeys = {
  me: ["me"] as const,
  dashboard: ["dashboard"] as const,
  portfolio: ["portfolio"] as const,
  jobs: ["jobs"] as const,
  key: ["key"] as const,
  profile: ["profile"] as const,
  preferences: ["preferences"] as const,
} as const;
