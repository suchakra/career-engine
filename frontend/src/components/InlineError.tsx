import { cn } from "@/lib/utils";

export interface InlineErrorProps {
  message: string;
  className?: string;
}

/** Inline validation / error surface, backed by the data layer (AD-16.8). */
export function InlineError({ message, className }: InlineErrorProps): JSX.Element {
  return (
    <p role="alert" className={cn("flex items-center gap-1.5 text-sm text-error", className)}>
      <span aria-hidden="true">✗</span>
      {message}
    </p>
  );
}
