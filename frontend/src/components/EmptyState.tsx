import { type ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  title: string;
  description?: string;
  /** Primary action (e.g. a Grill CTA). Optional. */
  action?: ReactNode;
  /**
   * When true, signals a load FAILURE (not merely empty data) — the caller should
   * disable Save so a failed read can never silently overwrite stored data
   * ("recoverable by default"). Rendered with an error affordance.
   */
  isError?: boolean;
  className?: string;
}

/**
 * Typed load-failure / empty read view. On failure the caller disables Save; this
 * component itself never mutates — it degrades gracefully and offers a next step.
 */
export function EmptyState({
  title,
  description,
  action,
  isError = false,
  className,
}: EmptyStateProps): JSX.Element {
  return (
    <div
      role={isError ? "alert" : undefined}
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-card border border-dashed border-border bg-card px-6 py-10 text-center",
        className,
      )}
    >
      <p className={cn("text-base font-medium", isError && "text-error")}>
        {isError ? "✗ " : ""}
        {title}
      </p>
      {description && <p className="max-w-md text-sm text-muted">{description}</p>}
      {action}
    </div>
  );
}
