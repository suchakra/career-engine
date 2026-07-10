/**
 * Feature flags — the frontend seam for premium/private and pre-launch features
 * (ARCHITECTURE §17 / AD-17.3). Read from `NEXT_PUBLIC_FEATURES` (comma-separated) at
 * build time. The OSS/demo build enables none; a commercial build sets the env. Nav
 * entries and routes gate on these so the same design system serves both.
 */

/** Known optional features (the reserved PREPARE/APPLY-extension surfaces). */
export type Feature = "outreach" | "interview" | "salary";

const enabled = new Set(
  (process.env.NEXT_PUBLIC_FEATURES ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
);

/** True when `feature` is enabled in this build. */
export function isFeatureEnabled(feature: Feature): boolean {
  return enabled.has(feature);
}
