import { useId, type InputHTMLAttributes, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  /** Optional helper/hint text under the input. */
  hint?: ReactNode;
}

/** A labeled text input form row used by progressive-disclosure forms. */
export function Field({ label, hint, className, id, ...props }: FieldProps): JSX.Element {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={inputId}
        className={cn(
          "min-h-tap rounded-card border border-border bg-surface px-3 text-sm text-text placeholder:text-muted",
          className,
        )}
        {...props}
      />
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </div>
  );
}
