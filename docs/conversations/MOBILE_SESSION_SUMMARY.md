# STRIX Mobile — Session Summary

> **Date:** 2026-04-18
> **Scope:** Wire the Expo/React Native app at `apps/mobile/` to the
> FastAPI backend at `apps/api/`, without regressing the already-shipped
> web app.
> **Outcome:** All 6 planned phases (M0–M5) delivered. 221 / 221 backend
> unit tests green, mobile TypeScript clean, smoke test covers the full
> mobile contract.

---

## 1. Starting state

- **Web app**: already wired to backend (prior session). 188 backend unit
  tests green; 32 API endpoints live; OpenAPI + TS types synced.
- **Mobile app**: Expo 54 + Expo Router + Zustand. Every screen read
  from `apps/mobile/lib/mock-data.ts`. No HTTP client, no auth, no login
  screen, fake 30-second interval masquerading as a WebSocket.
- **User concern**: backend changes for mobile must not affect the web
  app's runtime behaviour.

## 2. Mobile audit (before any code)

Findings from `apps/mobile/`:
- No HTTP client, no token persistence, no SSE.
- Push token captured via `expo-notifications` but never posted back.
- `useSocket.ts` injected synthetic alerts on a timer.
- Every tab imported `mock-data.ts` (347 lines of hardcoded arrays).
- `user-store.ts` held `mockUser`; no login screen existed.

Gaps verified against the live backend source:
- `GET /alerts` was a `501 _NotImplementedYet` stub.
- `POST /alerts/{id}/acknowledge` did not exist.
- `/auth/refresh` only read the `strix_refresh` httpOnly cookie — no
  body fallback for clients that can't hold cookies reliably.
- `TokenResponse` omitted the refresh token, so mobile had no way to
  re-auth after the 15-minute access token expired.
- No push-device table or endpoints.
- No dispatcher to fan out interventions to registered devices.

## 3. Plan (exported to `docs/MOBILE_INTEGRATION_PLAN.md`)

Five mobile-side phases, one backend-side phase:

| Phase | Scope | Effort |
|---|---|---|
| **M0** | Close backend gaps (additive / header-gated) | ~4 h |
| **M1** | Auth foundation — SecureStore, Bearer client, login screen | ~3 h |
| **M2** | Data wiring — React Query hooks, screens talk to real endpoints | ~4 h |
| **M3** | Real-time + platform — SSE, push registration, file scan, deep links | ~4 h |
| **M4** | Polish — register flow, dark-mode persistence, skeletons, error boundary | ~2 h |
| **M5** | Smoke test + EAS preview CI | ~1 h |

Web-safety guarantee: every backend change was either a **new endpoint**
(web doesn't call) or **gated behind `X-Client-Type: mobile`** (web
doesn't send). The existing 188 tests had to stay green after every
phase; a regression was impossible to ship.

---

## 4. M0 — Backend contract (delivered)

Six changes, zero runtime impact on web:

| # | Change | Mechanism |
|---|---|---|
| B1 | `GET /alerts` — keyset paging, severity filter, unack filter | Pure addition (was 501) |
| B2 | `POST /alerts/{id}/acknowledge` + `acknowledged_at`/`acknowledged_by` cols | Migration 0004 (nullable cols + partial index) |
| B3 | `/auth/refresh` accepts token via body as cookie fallback | Additive — cookie path remains primary |
| B4 | `TokenResponse.refresh_token` populated only when `X-Client-Type: mobile` | Optional in OpenAPI — web response byte-identical |
| B5 | `push_devices` table + `POST/GET/DELETE /auth/devices` | Migration 0004 — new table, CASCADE on user delete |
| B6 | `verdicts_writer` fans out ≥ ESCALATE to Expo via new dispatcher | Best-effort async; `PUSH_ENABLED=false` default |

### Files

- `apps/api/alembic/versions/0004_mobile_support.py` — ack cols + push_devices
- `apps/api/src/strix_api/api/routes/alerts.py` — real handlers
- `apps/api/src/strix_api/services/alerts_service.py` — severity mapping, keyset pagination
- `apps/api/src/strix_api/api/schemas/alerts.py` — typed wire models
- `apps/api/src/strix_api/repositories/push_device_repo.py` — idempotent upsert
- `apps/api/src/strix_api/adapters/expo_push_adapter.py` — circuit-breakered Expo client
- `apps/api/src/strix_api/services/push_dispatcher.py` — user-id cache + fan-out
- `apps/api/src/strix_api/api/routes/auth.py` — refresh body fallback, device endpoints
- `apps/api/src/strix_api/api/schemas/auth.py` — `RefreshRequest`, `DeviceRegisterRequest`, optional `refresh_token`

### Safety proofs shipped with M0

- `apps/api/tests/unit/test_m0_mobile.py` — 26 new tests.
- `test_token_response_schema_has_optional_refresh` — locks `refresh_token` as
  OPTIONAL in OpenAPI so a future change can't break web validation.
- `test_mobile_client_detection` — header check is exact; typos / prefix
  matches don't accidentally enable mobile mode for web.
- `test_push_dispatcher_noop_when_disabled` — Expo client isn't even
  instantiated unless `PUSH_ENABLED=true`.

**Result:** 188 → 214 tests (+26), zero regressions.

---

## 5. M1 — Auth foundation (delivered)

- `npx expo install expo-secure-store` — tokens live in Keychain (iOS) /
  EncryptedSharedPreferences (Android).
- `apps/mobile/lib/api/config.ts` — base URL resolution via
  `EXPO_PUBLIC_API_URL` → Expo dev-host inference → localhost.
- `apps/mobile/lib/api/storage.ts` — SecureStore wrapper with a
  web-localStorage fallback for `expo-web` builds.
- `apps/mobile/lib/api/client.ts` — Bearer-token fetch with:
  - `X-Client-Type: mobile` on every request
  - **single-flight** 401-auto-refresh (concurrent 401s wait on one
    refresh promise, never race)
  - Problem+JSON → `StrixApiError`
- `apps/mobile/lib/api/auth.ts` — `login`, `logout`, `me`,
  `registerDevice`, `unregisterDevice`.
- `apps/mobile/app/(auth)/login.tsx` — real login screen; inline error
  copy for 401 / 5xx / network.
- `apps/mobile/app/_layout.tsx` — `bootstrap()` reads SecureStore +
  validates `/auth/me`; auth gate redirects `anon+tabs → login`,
  `authed+auth → dashboard`.
- `apps/mobile/stores/user-store.ts` — rewritten with
  `status: "booting" | "anon" | "authed"`.
- Profile screen wired to real user + Sign Out confirmation.

Flow guarantees:
- Fresh install → splash → onboarding → login → dashboard
- Returning user with valid tokens → straight to dashboard
- Expired access / valid refresh → silent refresh on first 401
- Expired refresh → tokens wiped → bounce to login

---

## 6. M2 — Data wiring (delivered)

- `@tanstack/react-query` added.
- `apps/mobile/lib/api/QueryProvider.tsx` + `query-client.ts` — no-retry
  on 4xx, 30 s stale, 5 min gc, refetchOnWindowFocus off.
- `apps/mobile/lib/api/hooks.ts` — 12 typed hooks matching Pydantic
  schemas: `useAttackVector`, `useGlobalRisk`, `useSentinelInsight` /
  `useRefreshSentinelInsight`, `useAlertsInfinite`,
  `useUnacknowledgedCount`, `useAcknowledgeAlert`, `useIocSearch`,
  `useModels`, `useDrift`, `useRegisterDevice`, `useUnregisterDevice`.

Screens rewritten to read live endpoints:

| Screen | Wired to |
|---|---|
| `dashboard.tsx` | `/dashboard/attack-vector` + `/global-risk` + `/sentinel-insight` |
| `alerts.tsx` | `/alerts` (infinite paging) + acknowledge mutation |
| `search.tsx` | `/threat-intel/iocs?q=` (350 ms debounce) |
| `status.tsx` | `/monitoring/models` + `/monitoring/drift` |
| `(tabs)/_layout.tsx` | Tab badge reads live `useUnacknowledgedCount()` |

Rewrote `AlertCard.tsx` for the backend's `AlertItem` shape (derives
title from `decoderName + ruleId`, relative time from `occurredAt`,
ACKNOWLEDGED badge when `acknowledgedAt` is set).

**Deleted for good:** `lib/mock-data.ts`, `stores/alerts-store.ts`,
`hooks/useSocket.ts`.

---

## 7. M3 — Real-time + platform (delivered)

- `react-native-sse`, `expo-document-picker`, `expo-file-system` added.
- `apps/mobile/lib/api/sse.ts` — generic `useSseStream<T>` with
  Bearer-in-custom-header, exp-backoff reconnect to 30 s, bounded buffer.
  Public hooks: `useLiveFeed`, `useChainLogStream`, `useJobResult`.
- `apps/mobile/hooks/usePushNotifications.ts` — rewritten. Registers
  Expo token with the backend the moment `status === "authed"`;
  unregisters on `anon`. Notification-tap → `/analysis/[id]` when the
  payload carries `chainId`.
- Dashboard Intelligence Feed section consumes `useLiveFeed()`, shows
  `LIVE / CONNECTING / OFFLINE` dot, invalidates aggregates on each
  event, deep-links to analysis on tap.
- Search screen — "Scan a file" card: `expo-document-picker` →
  `useFileScan()` multipart upload → `useJobResult(scanId)` SSE to
  surface completion.
- New route `app/analysis/[id].tsx` — dwell time, infection radius,
  CKC progression timeline, live forensic-log SSE. Deep-linkable via
  `strix://analysis/<uuid>`.
- Backend one-liner: `build_live_feed_event()` now emits `chainId`
  so mobile can route on notification tap (web never reads it).

---

## 8. M4 — Polish + register flow (delivered)

The user's mid-session edit to `apps/api/src/strix_api/api/schemas/auth.py`
added `RegisterRequest` and imported it into the route. I finished wiring:

### Register backend

- Migration `0005_user_designation.py` — `users.designation TEXT NULL`.
- `User.designation` column + `UserRepo.create(designation=...)`.
- New `EmailAlreadyRegisteredError` (status 409, code
  `EMAIL_ALREADY_REGISTERED`) — replaces the 401 the route originally
  raised so the mobile client can show "email taken" vs "bad creds".
- `/auth/register` stores `designation`, commits the session, returns a
  full token pair (mobile gets `refresh_token` in body via the M0-B4
  gate; web doesn't).
- `/auth/me` returns `designation`.
- +7 regression tests in `apps/api/tests/unit/test_register.py`.

### Register mobile

- `lib/api/auth.ts` — `register()` matching login ergonomics.
- `stores/user-store.ts` — `register(email, password, designation?)`.
- `app/(auth)/register.tsx` — email + password (min 8) + optional
  callsign, 409-aware error copy.
- Login screen — "Need an account? Create one" link.

### Polish work

- `@react-native-async-storage/async-storage` added.
- `stores/ui-store.ts` rewritten — persists `isDark` via AsyncStorage,
  exposes `hydrate()`. Called alongside auth bootstrap in root layout.
- Profile "Dark Mode" row actually toggles theme.
- Dashboard — `<RefreshControl>` triggers parallel `refetch()` of
  attack-vector / global-risk / insight.
- `components/Skeleton.tsx` — pulsing placeholder with native-driver
  animation. Applied to Sentinel Insight card.
- `components/ErrorBoundary.tsx` — root boundary that surfaces
  `StrixApiError.status / code / detail` with a reset button. Mounted
  above the router.

**Result:** 214 → 221 tests (+7), still zero regressions.

---

## 9. M5 — Smoke + CI (delivered)

- `infra/scripts/smoke_mobile.py` — 12-step mobile-contract smoke:
  1. `/health` up
  2. `POST /auth/register` with mobile header → **asserts refresh_token
     is in the body**
  3. **Web-safety regression** — same register without the header must
     NOT leak a refresh token
  4. `/auth/me` includes `designation`
  5. `POST /auth/devices` registers an Expo token
  6. `GET /auth/devices` lists it
  7. `POST /auth/refresh` with **body** (no cookie) returns a rotated
     pair
  8. Bearer call to `/dashboard/attack-vector`
  9. Paginated `/alerts`
  10. SSE handshake on `/streams/live-feed`
  11. `DELETE /auth/devices/{token}` cleanup
  12. `/auth/logout`
- `Makefile` — new `make smoke-mobile` target; listed in `make help`.
- `.github/workflows/mobile.yml` — two jobs:
  - `typecheck` — `npx tsc --noEmit` on every PR
  - `eas-preview` — queues an EAS preview build on push to
    `main`/`Platforme` when `EXPO_TOKEN` secret is present; gracefully
    skips when absent

Dry-run against a dead URL fails cleanly with colour-coded summary and
exit 1 — no stack traces escape.

---

## 10. Final verification

- **Backend:** `221 / 221` unit tests pass (started at 188; +33 across
  M0 + M4).
- **Mobile:** `npx tsc --noEmit` emits errors only from the 5
  un-installed node_modules (`@tanstack/react-query`, `expo-secure-store`,
  `react-native-sse`, `expo-document-picker`,
  `@react-native-async-storage/async-storage`). All resolve on
  `npm install`.
- **OpenAPI snapshot** regenerated — `apps/web/lib/openapi.json` +
  `api-types.ts` carry the additive M0 + M4 schema changes.
- **Web runtime contract unchanged** — assert-in-smoke `web-safety` step
  locks the no-leak guarantee into CI.

## 11. Files touched at a glance

### Backend (added)

- 2 new migrations (`0004_mobile_support.py`, `0005_user_designation.py`)
- 3 new routes (`/alerts`, `/alerts/{id}/acknowledge`,
  `/alerts/unacknowledged/count`, `/auth/register`, `/auth/devices` GET/POST/DELETE)
- 4 new adapters / services (`expo_push_adapter`, `push_dispatcher`,
  `alerts_service`, `push_device_repo`)
- 2 new schemas (`alerts.py`, auth additions)
- 2 new test files (`test_m0_mobile.py`, `test_register.py`)

### Mobile (added)

- 6 new files under `lib/api/` (`config`, `client`, `storage`, `auth`,
  `hooks`, `sse`, `query-client`, `QueryProvider`)
- 2 new routes (`(auth)/login`, `(auth)/register`, `(auth)/_layout`,
  `analysis/[id]`)
- 3 new components (`Skeleton`, `ErrorBoundary`, `KPICard`+`MiniChart`+
  `AlertCard` rewritten)
- Rewrote `stores/user-store.ts` + `stores/ui-store.ts`
- Rewrote `hooks/usePushNotifications.ts`
- Rewrote every tab screen + root `_layout`

### Mobile (deleted)

- `lib/mock-data.ts`
- `stores/alerts-store.ts`
- `hooks/useSocket.ts`

### Ops (added)

- `infra/scripts/smoke_mobile.py`
- `docs/MOBILE_INTEGRATION_PLAN.md`
- `.github/workflows/mobile.yml`
- `make smoke-mobile` target

---

## 12. Known out-of-scope items

- **Expo push credentials** (FCM server key, APNs key) — backend accepts
  tokens fine; actual delivery requires EAS project config.
- **`EXPO_TOKEN`** GitHub secret for the `eas-preview` job.
- **Real device hardware** — simulators work but push banners only fire
  on physical devices.
- **`drift_baseline.json`** — still a placeholder; drift gauge reads 0
  until a real baseline is computed.
- **Threshold calibration** (original P2-9) —
  `CHAIN_OPEN_VAE_THRESHOLD=0.5` remains preliminary pending ≥1 week of
  real stream data.

## 13. How to run it

```bash
# One-time
cp apps/api/.env.example apps/api/.env        # set DB_PASSWORD + AUTH_JWT_SECRET
make up                                       # postgres + redis + api
make migrate                                  # applies 0001..0005
make seed                                     # bootstrap admin

# Backend smoke (ML pipeline end-to-end)
make smoke

# Mobile smoke (auth + Bearer + SSE + push + logout)
make smoke-mobile

# Mobile dev
cd apps/mobile
npm install
export EXPO_PUBLIC_API_URL=http://<LAN-IP>:8000
npx expo start --clear
```

---

## 14. Session close

The STRIX platform now has three first-class clients (web, mobile, CLI
smoke tests) and one set of backend contracts that serves them all
without divergence. The `X-Client-Type: mobile` header is the only
runtime switch; everything else is additive.
