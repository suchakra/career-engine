"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { configureApiClient } from "@/lib/api/client";

/** The minimal, display-safe user shape the UI needs (never the raw token). */
export interface AuthUser {
  uid: string;
  email: string | null;
}

export interface AuthContextValue {
  user: AuthUser | null;
  /** True until the initial auth state has resolved (avoids a login/dashboard flash). */
  loading: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  /** Returns a fresh (optionally force-refreshed) ID token, or null when signed out. */
  getToken: (forceRefresh?: boolean) => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Access the auth API. Throws if used outside an AuthProvider. */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

/**
 * Provides Firebase-backed auth state + actions, and wires the shared API client's
 * token provider + central auth-failure handler (AD-16.4 / AD-16.8).
 *
 * Firebase is imported dynamically inside effects/handlers so this module can be
 * mocked wholesale in tests without pulling the SDK (tests use a test double).
 */
export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  // Hold the raw Firebase user so getToken can call getIdToken without exposing it.
  const rawUserRef = useRef<import("firebase/auth").User | null>(null);

  useEffect(() => {
    let unsub: (() => void) | undefined;
    let active = true;

    void (async () => {
      try {
        const { getFirebaseAuth } = await import("@/lib/auth/firebase");
        const { onAuthStateChanged } = await import("firebase/auth");
        const auth = getFirebaseAuth();
        unsub = onAuthStateChanged(auth, (fbUser) => {
          if (!active) return;
          rawUserRef.current = fbUser;
          setUser(fbUser ? { uid: fbUser.uid, email: fbUser.email } : null);
          setLoading(false);
        });
      } catch {
        // Firebase init / SDK load failed (e.g. missing NEXT_PUBLIC_FIREBASE_*).
        // Resolve to a signed-out state so the app never hangs on the
        // "Checking your session…" placeholder; the login route takes over.
        if (!active) return;
        rawUserRef.current = null;
        setUser(null);
        setLoading(false);
      }
    })();

    return () => {
      active = false;
      unsub?.();
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    const getToken = async (forceRefresh = false): Promise<string | null> => {
      const current = rawUserRef.current;
      if (!current) return null;
      return current.getIdToken(forceRefresh);
    };

    const signIn = async (): Promise<void> => {
      const { getFirebaseAuth, googleProvider } = await import("@/lib/auth/firebase");
      const { signInWithPopup } = await import("firebase/auth");
      await signInWithPopup(getFirebaseAuth(), googleProvider());
    };

    const signOut = async (): Promise<void> => {
      const { getFirebaseAuth } = await import("@/lib/auth/firebase");
      const { signOut: fbSignOut } = await import("firebase/auth");
      await fbSignOut(getFirebaseAuth());
    };

    return { user, loading, signIn, signOut, getToken };
  }, [user, loading]);

  // Register the token provider + 401 handler with the shared fetch wrapper.
  useEffect(() => {
    configureApiClient({
      getToken: value.getToken,
      onAuthFailure: () => {
        void value.signOut();
      },
    });
  }, [value]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
