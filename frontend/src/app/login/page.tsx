"use client";

import { useState } from "react";

import { PrimaryButton } from "@/components/PrimaryButton";
import { ThemeToggle } from "@/components/ThemeToggle";
import { InlineError } from "@/components/InlineError";
import { RedirectIfAuthed } from "@/lib/auth/guard";
import { useAuth } from "@/lib/auth/context";

/** Public login / landing — one obvious way in (bitcrafty-branded, §4.0). */
export default function LoginPage(): JSX.Element {
  const { signIn } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSignIn = async (): Promise<void> => {
    setError(null);
    setBusy(true);
    try {
      await signIn();
    } catch {
      setError("Sign-in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <RedirectIfAuthed>
      <div className="flex min-h-screen flex-col">
        <div className="flex justify-end p-4">
          <ThemeToggle />
        </div>
        <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
          <div className="flex w-full max-w-md flex-col items-center gap-6">
            <div>
              <p className="text-2xl font-semibold">bitcrafty</p>
              <p className="text-sm text-muted">Engineering transformation for the AI era.</p>
            </div>
            <div>
              <h1 className="text-3xl font-semibold">CareerEngine</h1>
              <p className="mt-1 text-muted">
                Turn your experience into quantified, ATS-ready résumés.
              </p>
            </div>
            <PrimaryButton onClick={() => void onSignIn()} disabled={busy} className="w-full">
              {busy ? "Signing in…" : "Sign in with Google"}
            </PrimaryButton>
            {error && <InlineError message={error} />}
            <p className="text-xs text-muted">
              Privacy-first · bring your own Gemini key · your data stays yours.
            </p>
          </div>
        </main>
        <footer className="border-t border-border px-6 py-3 text-center text-xs text-muted">
          <a
            href="https://github.com/bitcrafty/career-engine"
            className="hover:text-text"
            target="_blank"
            rel="noreferrer"
          >
            Open source project hosted by bitcrafty · GitHub ↗
          </a>
        </footer>
      </div>
    </RedirectIfAuthed>
  );
}
