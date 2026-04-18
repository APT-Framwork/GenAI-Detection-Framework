import { QueryClient } from "@tanstack/react-query";

import { StrixApiError } from "./client";

/**
 * Shared QueryClient configured for mobile:
 *  - no retry on 4xx (user won't fix a 401 by retrying)
 *  - aggressive stale time: 30s for live dashboards, tuned per-query
 *  - gcTime 5min: dashboards re-fetch fast when backgrounded
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error instanceof StrixApiError && error.status >= 400 && error.status < 500) {
          return false;
        }
        return failureCount < 2;
      },
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
