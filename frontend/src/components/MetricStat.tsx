import { cn } from "@/lib/utils";

export interface MetricStatProps {
  label: string;
  value: string | number;
  /** Optional secondary caption (e.g. "14 stories · 3 checkpoints"). */
  caption?: string;
  className?: string;
}

/** A single metric rendered with tabular numerals so values align (§2). */
export function MetricStat({
  label,
  value,
  caption,
  className,
}: MetricStatProps): JSX.Element {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      <span className="tabnums text-2xl font-semibold">{value}</span>
      {caption && <span className="text-sm text-muted">{caption}</span>}
    </div>
  );
}
