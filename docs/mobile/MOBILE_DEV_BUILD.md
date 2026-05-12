# CAVIX mobile — dev build (Android)

How to rebuild the APK and start the app against it. This is the path you
take whenever you need **real system push notifications** (with sound,
even when the app is backgrounded). For day-to-day work that doesn't
need push, Expo Go is still fine — see [`MOBILE_DEVICE_SETUP.md`](./MOBILE_DEVICE_SETUP.md).

EAS project linked: `@yacine_na/strix-mobile` (projectId in
[`apps/mobile/app.json`](../../apps/mobile/app.json) under `expo.extra.eas`).

---

## 1. Rebuild the APK

Run from anywhere (the CLI cds into `apps/mobile` itself):

```bash
cd /home/yacine/Desktop/GenAI-Detection-Framework/apps/mobile
npx eas-cli@latest build --profile development --platform android
```

**What happens**

1. EAS compresses the project. With [`.easignore`](../../.easignore) in
   place the upload is ~25 MB. Without it, ~360 MB.
2. Uploads to EAS Build cloud → queues → builds (~10–15 min).
3. CLI prints a build URL:
   `https://expo.dev/accounts/yacine_na/projects/strix-mobile/builds/<id>`
   Open it in a browser to watch live logs.
4. On success, prints an `.apk` URL and offers
   `Install on Android device? (Y/n)` → **Y**. It renders a QR you scan
   with the phone camera; phone downloads the APK directly.

**If the install is blocked** on the phone:
- Settings → Apps → Special access → **Install unknown apps**
- Allow it for **Chrome** (or whichever browser handled the QR).

**When to rebuild**

You only need to rebuild the APK when **native code or config changes**:
- adding/removing/upgrading a native module (anything starting with
  `expo-*` or `react-native-*` that ships native code)
- editing `app.json` plugins or platform config (e.g. iOS infoPlist,
  Android channels)
- bumping the Expo SDK

You do **not** need to rebuild for JS/TS changes — those reload over
Metro the same way Expo Go reloads.

---

## 2. Start the app

The new APK is a "dev client" — on launch it looks for a Metro dev
server on your LAN. Two ways to start one:

### Path A — script (recommended)

```bash
cd /home/yacine/Desktop/GenAI-Detection-Framework
CAVIX_DEV_CLIENT=1 bash infra/scripts/mobile_dev.sh
```

The script:
- Resolves the laptop's LAN IP (override with `CAVIX_LAN_IP=…` or
  `CAVIX_LAN_IF=eth0`).
- Writes `apps/mobile/.env` with `EXPO_PUBLIC_API_URL=http://<lan-ip>:8000`
  so the app reaches your local backend.
- Verifies `/health` on `:8000` is reachable on that IP (warns if not).
- Renders a QR code in the terminal *and* saves a PNG to
  `/tmp/cavix-expo-qr.png`.
- Starts `npx expo start --lan --dev-client` and streams Metro logs.

If you're on a network where the phone can't see the laptop's LAN IP
(corporate Wi-Fi, hotel guest mode), use tunnel mode:

```bash
CAVIX_DEV_CLIENT=1 CAVIX_TUNNEL=1 bash infra/scripts/mobile_dev.sh
```

### Path B — manual

```bash
cd apps/mobile
npx expo start --lan --dev-client
```

You'll need to manually create `apps/mobile/.env` with
`EXPO_PUBLIC_API_URL=http://<laptop-LAN-IP>:8000` (the script does this
for you).

### Connecting from the phone

1. Open the **CAVIX dev build** app (the new APK you just installed),
   **not** Expo Go.
2. On the dev-client launch screen, **scan the QR** from your terminal
   (or tap "Enter URL manually" and paste the `exp://…` URL Metro prints).
3. Metro bundles, app loads. The first bundle is slow (~30 s); reloads
   are fast.
4. Press `r` in the Metro terminal to force a reload.

---

## 3. Verify push notifications work

After signing in to the app:

1. Check the Metro log for: `[push] got Expo push token, registering with API`
   — confirms the device registered.
2. Trigger a high-severity alert from the backend (or wait for the live
   feed to emit one). Within a second or two the phone should show a
   system tray notification with sound.
3. Background the app and trigger another. **Push must still ring** —
   that's the whole point of the dev build. If it doesn't, see
   troubleshooting below.

---

## 4. Troubleshooting

| Symptom                                                                | Cause / fix                                                                 |
|------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| Red `Console Error` mentioning `expo-notifications` at import          | You opened Expo Go, not the dev APK. Open the new CAVIX app instead.        |
| Dev client says "Couldn't connect to development server"               | Phone can't reach the laptop's LAN IP. Use `CAVIX_TUNNEL=1`.                |
| App loads but `/health` warning in script                              | Backend isn't running. From repo root: `make up`.                           |
| Push notifications never arrive even in dev build                      | Confirm `expo.extra.eas.projectId` in `app.json` matches the EAS project.   |
| `getExpoPushTokenAsync failed` in logs                                 | Permissions denied or wrong projectId. Reinstall app, grant notification permission when prompted. |
| Build fails on EAS                                                     | Open the build URL the CLI printed; gradle logs at the bottom usually point to the failing plugin or dependency. |

---

## 5. Useful EAS commands

```bash
# View past builds
npx eas-cli@latest build:list --platform android --limit 5

# Cancel an in-flight build
npx eas-cli@latest build:cancel <build-id>

# View this device's credentials (keystore, etc.)
npx eas-cli@latest credentials

# Rotate the Expo Push relay token, etc.
npx eas-cli@latest secret:list
```

---

## 6. Where things live

- [`apps/mobile/app.json`](../../apps/mobile/app.json) — plugin list,
  iOS/Android config, EAS projectId.
- [`apps/mobile/eas.json`](../../apps/mobile/eas.json) — build profiles
  (development / preview / production).
- [`.easignore`](../../.easignore) — excludes monorepo siblings from the
  build upload.
- [`apps/mobile/services/notifications.ts`](../../apps/mobile/services/notifications.ts) —
  lazy `tryGetNotifications()` + `IS_EXPO_GO`. Every consumer of
  `expo-notifications` must route through this so the app stays bootable
  in Expo Go.
- [`apps/mobile/hooks/usePushNotifications.ts`](../../apps/mobile/hooks/usePushNotifications.ts) —
  registers the device with the backend, handles taps on notifications.
- [`apps/api/src/strix_api/adapters/expo_push_adapter.py`](../../apps/api/src/strix_api/adapters/expo_push_adapter.py) —
  backend that POSTs to Expo's push relay (which forwards to FCM/APNs).
