"use client";

import { useState } from "react";

import { PrimaryButton } from "@/components/PrimaryButton";
import { cn } from "@/lib/utils";

export interface SplitButtonOption {
  label: string;
  onSelect: () => void;
}

export interface SplitButtonProps {
  label: string;
  /** Primary action (the main click). */
  onClick: () => void;
  /** Secondary actions revealed by the caret (e.g. PDF / Word / Markdown). */
  options: SplitButtonOption[];
  className?: string;
}

/**
 * A primary action with a caret that reveals related choices — realizes the
 * "Build résumé → PDF / Word / MD" split from the mockup while keeping one
 * primary action per screen.
 */
export function SplitButton({
  label,
  onClick,
  options,
  className,
}: SplitButtonProps): JSX.Element {
  const [open, setOpen] = useState(false);

  return (
    <div className={cn("relative inline-flex", className)}>
      <PrimaryButton className="rounded-r-none" onClick={onClick}>
        {label}
      </PrimaryButton>
      <PrimaryButton
        className="rounded-l-none border-l border-primary-fg/20 px-2"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="More options"
        onClick={() => setOpen((v) => !v)}
      >
        ▾
      </PrimaryButton>
      {open && (
        <ul
          role="menu"
          className="absolute right-0 top-full z-20 mt-1 min-w-[10rem] overflow-hidden rounded-card border border-border bg-card shadow-lg"
        >
          {options.map((opt) => (
            <li key={opt.label} role="none">
              <button
                type="button"
                role="menuitem"
                className="block w-full min-h-tap px-4 py-2 text-left text-sm hover:bg-surface"
                onClick={() => {
                  setOpen(false);
                  opt.onSelect();
                }}
              >
                {opt.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
