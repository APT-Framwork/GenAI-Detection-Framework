# `@/lib/api` — backend integration layer

Phase 4 (P4-5/6/7/8/11) wires the frontend to the live STRIX backend.
Pages should import from this module instead of `@/lib/mock-data`.

## Setup (one-time, in `app/layout.tsx`)

```tsx
import { QueryProvider } from "@/lib/api/provider";

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
```

## Hooks

| Hook | Hits | Cadence |
|---|---|---|
| `useAttackVector(window?)` | `GET /dashboard/attack-vector` | poll 30 s |
| `useGlobalRisk(window?)` | `GET /dashboard/global-risk` | poll 30 s |
| `useVictimGraph(window?)` | `GET /dashboard/victim-graph` | poll 60 s |
| `useSentinelInsight()` | `GET /dashboard/sentinel-insight` | poll 5 min |
| `useRefreshSentinelInsight()` | `POST /dashboard/sentinel-insight/refresh` | mutation |
| `useLiveFeed({enabled, maxEvents})` | SSE `/streams/live-feed` | push (auto-reconnect) |
| `useMe()` / `useLogin()` / `useLogout()` / `useHasRole()` | `/auth/*` | — |
| `useChainList({onlyOpen, limit})` | `GET /analysis/chains` | poll 30 s |
| `useOpenChainCount()` | derived from `useChainList` | poll 30 s |
| `useChainGraphEvolution(id)` | `GET /analysis/chains/{id}/graph-evolution` | poll 30 s |
| `useCkcProgression(id)` | `GET /analysis/chains/{id}/ckc-progression` | poll 30 s |
| `useChainPredictions(id)` | `GET /analysis/chains/{id}/predictions` | poll 30 s |
| `useChainInfection(id)` | `GET /analysis/chains/{id}/infection` | poll 60 s |
| `useChainDwellTime(id)` | `GET /analysis/chains/{id}/dwell-time` | poll 30 s |
| `useChainLogs(id, limit?)` | `GET /analysis/chains/{id}/logs` (paged) | infinite |
| `useChainLogStream(id)` | SSE `/streams/chains/{id}/logs` | push |

## SSE

```tsx
"use client";
import { useLiveFeed } from "@/lib/api/live-feed";

export function LiveFeed() {
  const { events, status } = useLiveFeed({ maxEvents: 50 });
  return (
    <ul>
      {events.map((e) => (
        <li key={e.id}>{e.data.alertId} — {e.data.ckcStageName}</li>
      ))}
    </ul>
  );
}
```

## Auth

Cookies are set by the backend on `/auth/login`; the client sends them
automatically on every request (`credentials: "include"`). The CSRF token
is read from the `strix_csrf` cookie and echoed as `X-CSRF-Token` on
mutating requests — **mutations from server-side code (RSC fetches) need
to set this header manually** because RSC has no `document.cookie`.

A 401 triggers exactly one refresh attempt; if that also 401s, the original
error bubbles up and the page should redirect to `/login`.

## Environment

`NEXT_PUBLIC_STRIX_API_BASE` overrides the API base URL.
Default: `/api/v1` (works behind a reverse proxy that maps `/api/v1` → backend).
