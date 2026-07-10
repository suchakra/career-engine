"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-card text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 min-h-tap px-4",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-fg hover:opacity-90",
        secondary: "border border-border bg-surface text-text hover:bg-card",
        ghost: "text-text hover:bg-card",
      },
    },
    defaultVariants: {
      variant: "primary",
    },
  },
);

export interface PrimaryButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Render as the child element (e.g. a Next <Link>) via Radix Slot. */
  asChild?: boolean;
}

/**
 * The single primary CTA per screen (also used for secondary/ghost actions).
 * ≥44px tap target and the shared focus-visible ring come from the base styles.
 */
export const PrimaryButton = forwardRef<HTMLButtonElement, PrimaryButtonProps>(
  ({ className, variant, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant }), className)}
        type={asChild ? undefined : (type ?? "button")}
        {...props}
      />
    );
  },
);
PrimaryButton.displayName = "PrimaryButton";

export { buttonVariants };
