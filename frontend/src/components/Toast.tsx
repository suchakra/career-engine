"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";

export type ToastVariant = "error" | "success" | "info";

export interface ToastMessage {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toasts: ToastMessage[];
  showToast: (message: string, variant?: ToastVariant) => void;
  dismissToast: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/** Access the toast API. Throws if used outside a ToastProvider. */
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}

let nextId = 0;

/** Provides the toast queue + renders the live region. Backed by the data layer. */
export function ToastProvider({ children }: { children: ReactNode }): JSX.Element {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, variant: ToastVariant = "info") => {
      const id = nextId++;
      setToasts((prev) => [...prev, { id, message, variant }]);
    },
    [],
  );

  const value = useMemo(
    () => ({ toasts, showToast, dismissToast }),
    [toasts, showToast, dismissToast],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={cn(
              "pointer-events-auto flex items-start justify-between gap-3 rounded-card border border-border bg-card px-4 py-3 text-sm shadow-lg",
              toast.variant === "error" && "border-error/40",
            )}
          >
            <span
              className={cn(
                toast.variant === "error" && "text-error",
                toast.variant === "success" && "text-strong",
              )}
            >
              {toast.variant === "error" ? "✗ " : toast.variant === "success" ? "✓ " : ""}
              {toast.message}
            </span>
            <button
              type="button"
              onClick={() => dismissToast(toast.id)}
              className="min-h-tap min-w-tap shrink-0 rounded px-1 text-muted hover:text-text"
              aria-label="Dismiss notification"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
