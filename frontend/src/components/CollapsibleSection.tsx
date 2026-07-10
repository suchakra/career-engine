"use client";

import * as Collapsible from "@radix-ui/react-collapsible";
import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface CollapsibleSectionProps {
  title: ReactNode;
  children: ReactNode;
  /** Optional trailing header content (e.g. an "(edit)" hint or badge). */
  headerRight?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}

/**
 * Progressive-disclosure section (Radix Collapsible) — the calm default view with
 * power actions one click away. Used by the profile + preferences forms.
 */
export function CollapsibleSection({
  title,
  children,
  headerRight,
  defaultOpen = false,
  className,
}: CollapsibleSectionProps): JSX.Element {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Collapsible.Root
      open={open}
      onOpenChange={setOpen}
      className={cn("rounded-card border border-border bg-card", className)}
    >
      <div className="flex items-center justify-between gap-3 px-4">
        <Collapsible.Trigger className="flex min-h-tap flex-1 items-center gap-2 text-left text-base font-medium">
          <ChevronRight
            className={cn("h-4 w-4 shrink-0 transition-transform", open && "rotate-90")}
            aria-hidden="true"
          />
          {title}
        </Collapsible.Trigger>
        {headerRight}
      </div>
      <Collapsible.Content className="px-4 pb-4 pt-1">{children}</Collapsible.Content>
    </Collapsible.Root>
  );
}
