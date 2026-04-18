# STRIX Mobile Integration Plan

> **Date:** 2026-04-18
> **Target:** Wire the Expo/React Native app at `apps/mobile/` to the FastAPI backend at `apps/api/`
> **Web-app impact:** Zero at runtime. All backend changes are additive or gated behind `X-Client-Type: mobile`.

---

## 1. Current state of the mobile app

**Stack:** Expo 54 · React Native 0.81 · Expo Router · Zustand 5 · Expo Notifications · React Native SVG.

**Screens:**
- Splash → 3 onboarding slides → 5 tabs (dashboard, alerts, search, status, profile).

**Key gap files:**
- `apps/mobile/hooks/useSocket.ts` — fake 30s-interval alert generator, not a real socket
- `apps/mobile/hooks/usePushNotifications.ts` — captures Expo push token but never sends it to backend
- `apps/mobile/stores/user-store.ts` — hardcoded `mockUser`, no token storage
- `apps/mobile/lib/mock-data.ts` — 347 lines of hardcoded data, imported by every screen

**What's missing entirely:**
- HTTP client / API layer (no `axios`, no `react-query`, no fetch wrapper)
- Token storage (no `expo-secure-store`)
- Login screen
- Real SSE consumer (React Native has no native `EventSource`)
- File picker for threat-intel scans
- Device registration for push notifications

---

## 2. Backend gaps blocking mobile (M0 work)

Verified against live source. All additive or header-gated — zero web-app runtime impact.

| # | Gap | Evidence | Effort |
|---|---|---|---|
| **B1** | `GET /alerts` is a **501 stub** | `apps/api/src/strix_api/api/routes/alerts.py:18-20` raises `_NotImplementedYet` | ~1h |
| **B2** | No `POST /alerts/{id}/acknowledge` | Route doesn't exist; `alerts` table has no `acknowledged_at` column | ~30min |
| **B3** | Refresh flow is **cookie-only** | `apps/api/src/strix_api/api/routes/auth.py:122` reads `_REFRESH_COOKIE`; mobile can't hold httpOnly cookies | ~30min |
| **B4** | `TokenResponse` **omits the refresh token** | `auth.py:111-114` returns only `access_token` + `expires_in`. Mobile needs refresh token in body for SecureStore | ~15min |
| **B5** | No push-device registration | Table + endpoints don't exist | ~1h |
| **B6** | No push dispatcher | Expo push API integration missing | ~1h |

**Total M0 backend work: ~4 hours.**

### Why each one is web-safe

- **B1:** Web uses `useLiveFeed()` (SSE) + `useNotifications()` — never calls `/alerts`. Promoting 501 → 200 can't break what doesn't call it.
- **B2:** New endpoint + new nullable columns. Zero-downtime Alembic.
- **B3:** Cookie path stays primary; body is fallback. Web cookie flow untouched.
- **B4:** `refresh_token` field only populated when `X-Client-Type: mobile` header is set. Web sends no such header → gets identical response.
- **B5:** Pure addition. Web doesn't call these.
- **B6:** Background worker change, no API surface modified.

### Non-runtime caveats

1. **OpenAPI snapshot regen** needed after B4 + B5. Single command: `make openapi`.
2. **Alembic migration 0004** adds 2 nullable columns to `alerts` + new `push_devices` table. ACCESS EXCLUSIVE lock on `alerts` is milliseconds on current volume.

---

## 3. Mobile-side work — 5 phases

### Phase M1 — Auth foundation (~3h)

1. `npx expo install expo-secure-store`
2. `apps/mobile/lib/api/client.ts` — Bearer-token fetch wrapper
   - Sends `X-Client-Type: mobile` on login so backend returns refresh token in body
   - Auto-refresh on 401 (single-flight, deduplicated)
   - Problem+JSON error mapping
3. `apps/mobile/lib/api/auth.ts` — `login` / `logout` / `me` / `refresh`
   - Tokens in SecureStore (Keychain/EncryptedSharedPreferences)
4. `apps/mobile/app/(auth)/login.tsx` — new login screen
5. Rework `apps/mobile/app/_layout.tsx` to gate tabs behind `useMe()`
6. Rewrite `stores/user-store.ts` to drop mockUser and sync from `/auth/me`

### Phase M2 — Data wiring (~4h)

Swap mock imports for real hooks, one tab at a time. Install `@tanstack/react-query` (~40KB) for cache + retry.

| Tab | Endpoints wired |
|---|---|
| Dashboard | `GET /dashboard/attack-vector`, `/dashboard/global-risk`, `/dashboard/sentinel-insight` |
| Alerts | `GET /alerts` (paginated), `POST /alerts/{id}/acknowledge` |
| Search | `GET /threat-intel/iocs?q=` |
| Status | `GET /monitoring/models`, `/monitoring/drift` |
| Profile | `GET /auth/me`, `POST /auth/logout` |

**Delete `apps/mobile/lib/mock-data.ts`** when this phase closes.

### Phase M3 — Real-time & platform features (~4h)

1. `npm i react-native-sse` — EventSource polyfill
2. Replace `hooks/useSocket.ts` with real `useLiveFeed()` consuming `GET /streams/live-feed`
3. 10s polling fallback on `/alerts?since=<lastId>` when SSE disconnects >30s (battery-friendly)
4. `npx expo install expo-document-picker expo-file-system` — file upload on Search → `POST /threat-intel/files/scan` + `/streams/jobs/{jobId}` SSE
5. Register Expo push token on login → `POST /auth/devices`; unregister on logout
6. Deep linking: `strix://analysis/chain/<id>` → new `app/(tabs)/analysis/[id].tsx`

### Phase M4 — Polish (~2h)

- Persist UI store (dark mode) via `@react-native-async-storage/async-storage`
- Pull-to-refresh on Dashboard, Alerts, Status
- Skeleton loaders + error boundaries (surface Problem+JSON `title`/`detail`)
- Logout clears SecureStore + calls `DELETE /auth/devices/{token}` before navigating to login

### Phase M5 — Smoke test (~1h)

- Extend `make smoke` with `--mobile` flag: curl auth flow with `X-Client-Type: mobile`, confirm refresh token in body, hit 3 Bearer-auth'd endpoints
- Add Expo EAS preview build step to CI

---

## 4. Effort summary

| Phase | Effort | Blocks |
|---|---|---|
| M0 — Backend gaps | 4h | everything |
| M1 — Auth | 3h | M2+ |
| M2 — Data wiring | 4h | M3 (SSE needs tokens) |
| M3 — Real-time + push + files | 4h | M4 |
| M4 — Polish | 2h | — |
| M5 — Smoke | 1h | ship |
| **Total** | **~18h (2–3 working days)** | |

---

## 5. Guarantees for web-app safety

- **188 existing unit tests must stay green** after every M0 change
- **+3 new regression tests** added specifically for web-contract protection:
  1. Login without `X-Client-Type: mobile` returns body with **no** `refresh_token` key
  2. Refresh using cookie path continues to work unchanged
  3. Existing auth middleware test matrix still passes
- After M0: `make smoke` re-run to verify web dashboard's SSE + auth flow still work end-to-end

---

## 6. Screen → endpoint mapping

| Mobile screen | Primary endpoints | Auth | Real-time |
|---|---|---|---|
| Login | `POST /auth/login` | — | — |
| Dashboard | `GET /dashboard/{attack-vector, global-risk, sentinel-insight}` | Bearer | `/streams/live-feed` (SSE) |
| Alerts | `GET /alerts`, `POST /alerts/{id}/acknowledge` | Bearer | SSE + polling fallback |
| Search | `GET /threat-intel/iocs` | Bearer | — |
| Network/Status | `GET /monitoring/{models, drift}` | Bearer | — |
| Profile | `GET /auth/me`, `POST /auth/logout`, `DELETE /auth/devices/{token}` | Bearer | — |
| Threat-intel file scan | `POST /threat-intel/files/scan`, `/streams/jobs/{id}` | Bearer | SSE |
| Chain deep-link | `GET /analysis/chains/{id}/*` | Bearer | `/streams/chains/{id}/logs` (SSE) |
| Push registration | `POST /auth/devices` | Bearer | — |

---

## 7. Known unknowns / deferred

- **Expo push credentials** (FCM server key for Android, APNs key for iOS) — needed for B6 to actually deliver; backend will still accept token registrations without them
- **EAS build profile** — `eas.json` not yet configured; M5 step
- **Offline mode** — out of scope for 1.0; React Query cache will smooth over flaky networks
