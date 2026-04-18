// -----------------------------------------------------------------------------
// QueryProvider — drop into the root layout to enable Tanstack Query app-wide.
//
//     // app/layout.tsx
//     import { QueryProvider } from "@/lib/api/provider";
//     <QueryProvider>{children}</QueryProvider>
// -----------------------------------------------------------------------------

"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Pause polling on hidden tabs (matches §12 Q6 cadence).
            refetchOnWindowFocus: true,
            refetchIntervalInBackground: false,
            retry: (failureCount) => failureCount < 2,
            staleTime: 15_000,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
