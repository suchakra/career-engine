import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { type ReactElement, type ReactNode } from "react";

import { ToastProvider } from "@/components/Toast";
import { configureApiClient } from "@/lib/api/client";

/** A QueryClient with retries off so tests fail fast and deterministically. */
export function makeTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // gcTime: Infinity so optimistic setQueryData values survive for assertions
      // — with no useQuery observer, gcTime:0 would GC the cache entry immediately.
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
}

/**
 * Render a component tree with the app's client providers (React Query + toasts)
 * and a fake API token so apiFetch attaches an Authorization header that MSW sees.
 * Auth context is mocked per-test via vi.mock("@/lib/auth/context").
 */
export function renderWithProviders(
  ui: ReactElement,
  { client = makeTestQueryClient() }: { client?: QueryClient } = {},
): RenderResult & { client: QueryClient } {
  configureApiClient({
    getToken: async () => "test-token",
    onAuthFailure: () => {},
  });

  function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <QueryClientProvider client={client}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    );
  }

  return Object.assign(render(ui, { wrapper: Wrapper }), { client });
}
