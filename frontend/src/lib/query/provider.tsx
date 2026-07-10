"use client";

import {
  HydrationBoundary,
  QueryClient,
  QueryClientProvider,
  type DehydratedState,
} from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/** Sensible defaults: no aggressive refetch storms, one retry on transient error. */
function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

/**
 * App-wide React Query provider. `dehydratedState` is the SSR seam: server
 * components fetch initial data and pass it here so first paint is data, not a
 * spinner (AD-16.8). Optional so client-only trees (and tests) can omit it.
 */
export function Providers({
  children,
  dehydratedState,
}: {
  children: ReactNode;
  dehydratedState?: DehydratedState;
}): JSX.Element {
  // One client per component lifetime (survives re-renders, not shared across users).
  const [queryClient] = useState(makeQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <HydrationBoundary state={dehydratedState}>{children}</HydrationBoundary>
    </QueryClientProvider>
  );
}
