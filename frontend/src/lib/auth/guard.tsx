"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/lib/auth/context";

/** Full-screen "checking your session" placeholder shown while auth resolves. */
function AuthPending(): JSX.Element {
  return (
    <div
      className="flex min-h-[40vh] items-center justify-center text-sm text-muted"
      role="status"
      aria-live="polite"
    >
      Checking your session…
    </div>
  );
}

/**
 * Gate protected routes: while auth is resolving, render a placeholder; once
 * resolved, redirect unauthenticated users to /login and only then render.
 */
export function RequireAuth({ children }: { children: ReactNode }): JSX.Element {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading) return <AuthPending />;
  if (!user) return <AuthPending />;
  return <>{children}</>;
}

/**
 * Guard the public login route: redirect already-authenticated users to the
 * dashboard so login is never shown to a signed-in user.
 */
export function RedirectIfAuthed({ children }: { children: ReactNode }): JSX.Element {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) {
      router.replace("/dashboard");
    }
  }, [loading, user, router]);

  if (loading) return <AuthPending />;
  if (user) return <AuthPending />;
  return <>{children}</>;
}
