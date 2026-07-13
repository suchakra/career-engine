import Link from "next/link";

/**
 * 404 (UX-1).
 *
 * Next renders its default not-found page OUTSIDE the app chrome, so a mistyped or stale URL
 * used to land the user on a page with **no navigation whatsoever**. On a desktop they can hit
 * Back; on a phone — where the nav did not exist either (the bug this ticket is about) — it was
 * a dead end. The way out has to be in the page itself.
 */
export default function NotFound(): JSX.Element {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-sm text-muted">
        That link doesn&apos;t go anywhere. It may have moved, or the address may be mistyped.
      </p>
      <Link
        href="/dashboard"
        className="min-h-tap rounded-card border border-border px-4 py-2 text-sm hover:bg-card"
      >
        Back to Dashboard
      </Link>
    </main>
  );
}
