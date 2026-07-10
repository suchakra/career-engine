import { cn } from "@/lib/utils";

/**
 * Status semantics reused across Jobs tiers AND Portfolio entry status. Color is
 * ALWAYS paired with a label and a glyph (● / ◑ / ✓ / ✗) so it never reads by
 * color alone (accessibility + colorblind-safe, PHASE10_UI_MOCKUP.md §2).
 */
export type StatusKind = "strong" | "review" | "skipped" | "error";

const STATUS: Record<StatusKind, { glyph: string; className: string; srLabel: string }> = {
  strong: { glyph: "●", className: "text-strong", srLabel: "Strong" },
  review: { glyph: "◑", className: "text-review", srLabel: "For review" },
  skipped: { glyph: "✓", className: "text-skipped", srLabel: "Skipped" },
  error: { glyph: "✗", className: "text-error", srLabel: "Error" },
};

export interface StatusBadgeProps {
  status: StatusKind;
  /** Visible label; falls back to a sensible default for the status. */
  label?: string;
  className?: string;
}

export function StatusBadge({ status, label, className }: StatusBadgeProps): JSX.Element {
  const meta = STATUS[status];
  const text = label ?? meta.srLabel;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-xs font-medium",
        meta.className,
        className,
      )}
    >
      <span aria-hidden="true">{meta.glyph}</span>
      <span>{text}</span>
    </span>
  );
}
