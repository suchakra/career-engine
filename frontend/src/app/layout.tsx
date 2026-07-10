import type { Metadata } from "next";

import { AuthProvider } from "@/lib/auth/context";
import { Providers } from "@/lib/query/provider";
import { ToastProvider } from "@/components/Toast";
import { themeInitScript } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "CareerEngine",
  description: "Turn your experience into quantified, ATS-ready résumés.",
};

/**
 * Root layout: sets the theme class before paint (no flash), then wires the
 * app-wide providers — React Query (server-cache), Firebase auth, and toasts.
 * Per-screen chrome (sidebar/top bar/footer) is provided by AppShell on the
 * protected routes; the public login route renders its own minimal chrome.
 */
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Inline theme script runs before paint to avoid a flash-of-wrong-theme. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>
          <AuthProvider>
            <ToastProvider>{children}</ToastProvider>
          </AuthProvider>
        </Providers>
      </body>
    </html>
  );
}
