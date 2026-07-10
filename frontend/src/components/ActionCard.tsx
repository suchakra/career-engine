import { type ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface ActionCardProps {
  title?: ReactNode;
  children: ReactNode;
  /** Optional trailing content in the header (e.g. a count or badge). */
  headerRight?: ReactNode;
  className?: string;
}

/** 12px-radius card container; screens compose these rather than re-implementing. */
export function ActionCard({
  title,
  children,
  headerRight,
  className,
}: ActionCardProps): JSX.Element {
  return (
    <section className={cn("rounded-card border border-border bg-card p-5", className)}>
      {(title || headerRight) && (
        <header className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="text-base font-medium">{title}</h2>}
          {headerRight}
        </header>
      )}
      {children}
    </section>
  );
}
