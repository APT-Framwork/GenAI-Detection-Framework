# Running STRIX mobile on a physical device

> Goal: get the Expo app at `apps/mobile/` running on your real phone,
> talking to the backend at `apps/api/`.
>
> Two paths below:
> - **Path A — Expo Go** (5 min, works for ~95% of the app)
> - **Path B — Dev build** (30 min, required only for real push notifications)
>
> Start with A. Switch to B only once you've confirmed A works and you
> actually need push.

---

## 0. What you need before you start

- Backend running locally (`make up` → `curl http://localhost:8000/health`
  returns 200).
- Your laptop and your phone on **the same Wi-Fi network**. Corporate
  Wi-Fi that isolates clients ("guest mode") won't work — use your home
  network or a personal hotspot.
- Laptop's **LAN IP address**. You'll use it in one environment variable.
- Node 20+ installed on the laptop.
- Expo Go app installed on the phone (App Store / Play Store). Free, no
  account needed.

### Find your laptop's LAN IP

```bash
# Linux / macOS
ip -4 addr show | grep -E 'inet 192|inet 10'       # or: ifconfig | grep 'inet '
# → e.g.  inet 192.168.1.42/24

# Windows (PowerShell)
ipconfig | findstr /C:"IPv4"
```

Pick the IP on the interface that's actually connected to Wi-Fi
(typically starts with `192.168.` or `10.`). We'll call it `$LAN_IP`
below.

---

## Path A — Expo Go (start here)

### A.1 Make the backend reachable from the phone

The API container already binds `0.0.0.0:8000` (confirmed in
`apps/api/Dockerfile`), so the backend is listening on every interface.
What's usually missing is a firewall exception.

```bash
# Quick sanity check from the laptop — hit the API via its LAN IP,
# not localhost. If this fails, the phone won't reach it either.
curl http://$LAN_IP:8000/health
# → {"status":"ok"}
```

If it **hangs or fails**, your firewall is blocking port 8000:

```bash
# Linux (ufw)
sudo ufw allow 8000/tcp

# Linux (iptables)
sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT

# macOS — System Settings → Network → Firewall → allow incoming on port 8000,
# or temporarily: sudo pfctl -d   (disables the firewall; re-enable with -e)

# Windows — Windows Defender Firewall → Inbound Rules → New Rule → Port 8000 TCP → Allow
```

Re-run the `curl` from the laptop until it works.

### A.2 Point the mobile app at the LAN IP

```bash
cd apps/mobile
npm install                                  # first time only

# THIS is the critical line. Without it, the app falls back to
# localhost or the Metro debugger-host, which won't reach the container
# on a physical device.
export EXPO_PUBLIC_API_URL=http://$LAN_IP:8000

# Start the Expo dev server
npx expo start --clear
```

You'll see a QR code in the terminal plus a URL like
`exp://192.168.1.42:8081`.

### A.3 Open the app on the phone

- **Android**: open Expo Go → "Scan QR Code" → point it at the terminal QR.
- **iOS**: open the **Camera app** (not Expo Go) → point at the QR →
  tap the banner that asks to open Expo Go. (iOS blocks Expo Go from
  scanning QR codes directly; the system camera works.)

The app should bundle (~20 seconds the first time), open on the splash
screen, and land on the login screen.

### A.4 Create an account

On the login screen, tap **"Need an account? Create one"** → fill in
email + password (≥ 8 chars) + an optional call sign → tap
**CREATE ACCOUNT**. You'll land on the dashboard.

Alternatively, use the bootstrap admin (`make seed` on the laptop):
email `admin@strix.local`, password `changeme` (or whatever you set
via `ADMIN_PASSWORD`).

### A.5 Verify the wire-up

- **Dashboard**: threat gauge + KPIs populate. "Intelligence Feed"
  should show `CONNECTING` → `LIVE` within a few seconds. If it stays
  `OFFLINE`, SSE isn't reaching the phone — usually a firewall issue.
- **Alerts**: empty list with "No alerts" is correct if no alerts have
  been ingested yet. Run `make smoke` on the laptop in a second
  terminal to inject one.
- **Network (Status)**: should list AE / VAE / Transformer / GNN / DQN
  models with p50 / p99 / drift metrics.

### A.6 If the phone can't reach the laptop

Fallback: Expo tunnel (slower, but routes through Expo's servers so
firewall / Wi-Fi isolation don't matter).

```bash
# One-time install
npm i -g @expo/ngrok@^4.1.0

# Restart Expo with the tunnel flag
EXPO_PUBLIC_API_URL=http://$LAN_IP:8000 npx expo start --tunnel --clear
```

Note: the **tunnel only tunnels the Metro bundler** (the JavaScript),
not your API. The phone still needs to reach your API directly. If
you're on a coffee-shop Wi-Fi that blocks peer traffic, use your phone
as a personal hotspot and connect the laptop to it — then repeat steps
A.1–A.3 with the new LAN IP.

---

## Path A limitations

Works in Expo Go:
- Auth, SecureStore, Bearer + single-flight refresh
- Every REST endpoint (dashboard, alerts, search, threat-intel, status)
- SSE live feed + per-chain log stream
- File picker + upload to `/threat-intel/files/scan`
- Deep linking for `strix://analysis/<uuid>`

Does **not** work in Expo Go:
- **Remote push notifications on Android** — Expo deprecated this in
  SDK 53+. Local notifications (`Notifications.scheduleNotificationAsync`)
  still work; the full "backend sends a push → phone banner" flow needs
  a dev build.

If you need remote push, continue to Path B.

---

## Path B — Dev build (only for real push notifications)

A "dev build" is a custom build of the Expo client that includes your
project's config + credentials. It runs like Expo Go but supports
native modules Expo Go can't.

### B.1 Create an Expo account + EAS project

```bash
npm i -g eas-cli
eas login                                     # follow the prompts

cd apps/mobile
eas init                                      # creates an EAS project,
                                              # writes projectId to app.json
```

After `eas init`, your `app.json` will gain:

```jsonc
"extra": {
  "eas": { "projectId": "your-uuid-here" }
}
```

Commit this — the project ID is public.

### B.2 Configure EAS build profiles

Create `apps/mobile/eas.json`:

```json
{
  "cli": {
    "version": ">= 5.9.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "ios": { "simulator": false },
      "android": { "buildType": "apk" }
    },
    "preview": {
      "distribution": "internal",
      "ios": { "simulator": false },
      "android": { "buildType": "apk" }
    }
  }
}
```

### B.3 Build + install

```bash
# Android — builds an APK you can sideload
eas build --platform android --profile development
# When done, EAS prints a URL; scan the QR on the phone to install.

# iOS — requires Apple Developer account ($99/yr) to install on a real device
eas build --platform ios --profile development
```

Once installed, **open the dev client on the phone** (it's a separate
app from Expo Go), then scan the QR from `npx expo start` to load
your JS bundle into it.

### B.4 Configure push credentials

**Android (FCM)**:

1. Go to Firebase Console → create a new project → add Android app
   with package name `com.strix.mobile`.
2. Download `google-services.json` → place in `apps/mobile/`.
3. In Firebase → Project Settings → Cloud Messaging → copy the
   **Server key**.
4. Upload it to EAS:
   ```bash
   cd apps/mobile
   eas credentials
   # → Android → Push Notifications (FCM) → paste server key
   ```

**iOS (APNs)**:

1. In the Apple Developer Portal, create a new Push Notifications Auth
   Key (`.p8` file). Keep the Key ID + Team ID.
2. Upload to EAS:
   ```bash
   eas credentials
   # → iOS → Push Notifications → paste the .p8 + Key ID + Team ID
   ```

Rebuild after adding credentials:

```bash
eas build --platform all --profile development --clear-cache
```

### B.5 Test the push end-to-end

- Log in on the phone — `usePushNotifications.ts` will call
  `POST /auth/devices` with your Expo token.
- Confirm it landed on the backend:
  ```bash
  # Get an access token via smoke login or curl
  curl http://$LAN_IP:8000/api/v1/auth/devices \
    -H "Authorization: Bearer <your-token>"
  # → [{"deviceId":"...","expoPushToken":"ExponentPushToken[...]","platform":"ios",...}]
  ```
- On the backend, enable push:
  ```bash
  # In apps/api/.env
  PUSH_ENABLED=true
  ```
  Restart the `verdicts-writer` worker (`docker compose restart strix_verdicts_writer`).
- Inject an alert and watch for the banner:
  ```bash
  # From the repo root
  python infra/scripts/smoke.py
  ```
  If the ML pipeline decides on ESCALATE or higher, the
  `PushDispatcher` will fan out to your device. You should see a
  banner on the phone within a couple of seconds.

---

## Troubleshooting

### Everything feels broken: work the stack

Run these in order and stop at the first failure:

```bash
# 1. Backend is up and healthy on localhost
curl http://localhost:8000/health
# → {"status":"ok"}

# 2. Backend is reachable on the LAN IP
curl http://$LAN_IP:8000/health

# 3. Phone can reach the laptop at all (paste into any phone browser)
#    It should return {"status":"ok"}.
http://$LAN_IP:8000/health

# 4. EXPO_PUBLIC_API_URL was set BEFORE `expo start`
echo $EXPO_PUBLIC_API_URL
# → should print http://192.168.x.x:8000

# 5. Expo bundler is running
# → `npx expo start` shows a QR code and "Metro waiting on exp://..."
```

If step 3 fails, it's **always** firewall or Wi-Fi isolation.

### "Network request failed" in the app

Almost always `EXPO_PUBLIC_API_URL` wasn't set when Expo bundled. The
value is baked into the JS bundle at start time — changing your shell
env after that does nothing. Kill Metro, re-export, `npx expo start
--clear`.

### "All connection attempts failed" in `make smoke-mobile`

The smoke script tests the backend contract directly (not the phone).
If it fails, fix the backend first, then come back to the device.

### iOS: "Connection is not secure" / app quietly does nothing

Expo Go ships with ATS exceptions that allow HTTP to LAN IPs, so this
shouldn't happen there. If you've moved to a dev build, add to
`app.json`:

```jsonc
"ios": {
  "bundleIdentifier": "com.strix.mobile",
  "supportsTablet": true,
  "infoPlist": {
    "NSAppTransportSecurity": {
      "NSAllowsLocalNetworking": true
    }
  }
}
```

Then rebuild.

### Android: cleartext traffic blocked

Same story — Expo Go is fine. For a dev build, in `app.json`:

```jsonc
"android": {
  "package": "com.strix.mobile",
  "usesCleartextTraffic": true
}
```

### SSE says "OFFLINE" forever

The `/streams/live-feed` endpoint needs the same Bearer token as REST,
plus it holds the connection open. Some corporate Wi-Fi / MDM profiles
break long-polling connections. Test with:

```bash
curl -N http://$LAN_IP:8000/api/v1/streams/live-feed \
  -H "Authorization: Bearer <your-token>"
```

If curl streams events but the phone stays OFFLINE, the phone network
is interfering. Personal hotspot usually fixes it.

### Dark mode or login state doesn't persist

Expo Go cold-starts wipe JS state but not SecureStore / AsyncStorage.
If you're seeing wipes, you're probably reinstalling the app each time
— that *does* clear storage on both iOS and Android.

### `usePushNotifications` doesn't prompt for permission

The prompt only fires on a real device (`Device.isDevice` guard in
`usePushNotifications.ts`). In a simulator it silently no-ops. If
you're on a real device and still don't see the prompt, check
Settings → Notifications → Expo Go (or your dev build) and toggle
permissions manually.

### Deep link `strix://analysis/<uuid>` doesn't open the app

- In Expo Go, the scheme is `exp://` not `strix://`. Deep links work
  only in dev builds and production builds.
- In a dev build, test with:
  ```bash
  # Android
  adb shell am start -W -a android.intent.action.VIEW \
    -d "strix://analysis/11111111-1111-1111-1111-111111111111"

  # iOS simulator
  xcrun simctl openurl booted "strix://analysis/11111111-1111-1111-1111-111111111111"
  ```

---

## Reproducing the contract smoke on the device

The CLI smoke test (`make smoke-mobile`) exercises every endpoint the
app uses. When something's wrong, it tells you whether the problem is
backend-side or app-side:

```bash
make smoke-mobile
# → 12-step checklist, all green on a healthy backend
```

If `make smoke-mobile` passes but the app still doesn't work, the
issue is almost always one of:
1. Wrong `EXPO_PUBLIC_API_URL`
2. Firewall blocking port 8000 from the phone
3. Phone on a different Wi-Fi

---

## Quick reference — full device bring-up

```bash
# --- Terminal 1: backend ---
cd /home/yacine/Desktop/GenAI-Detection-Framework
cp apps/api/.env.example apps/api/.env      # first time only
make up
make migrate
make seed                                    # creates admin@strix.local / changeme
curl http://localhost:8000/health            # expect {"status":"ok"}

# --- Terminal 2: find LAN IP + verify + mobile ---
ip -4 addr show | grep -E 'inet 192|inet 10'
export LAN_IP=192.168.1.42                   # ← your actual IP
curl http://$LAN_IP:8000/health              # MUST succeed
sudo ufw allow 8000/tcp                      # if the above failed

cd apps/mobile
npm install                                  # first time only
export EXPO_PUBLIC_API_URL=http://$LAN_IP:8000
npx expo start --clear

# --- Phone ---
# Install Expo Go → scan QR → app opens → log in or register
```

You're running.
