/**
 * API base URL resolution.
 *
 * In dev, Expo's tunnel / LAN IP makes `localhost` resolve to the device,
 * not the dev host. We pick up `EXPO_PUBLIC_API_URL` from .env so each
 * developer can point the app at whatever their API is reachable on
 * (tunnel URL, LAN IP, or production URL).
 *
 * Priority:
 *   1. `EXPO_PUBLIC_API_URL` env var
 *   2. Host-machine debugger URL (dev only, best-effort)
 *   3. Hard-coded localhost fallback — only useful for web preview
 */

import Constants from "expo-constants";

function guessDevHostUri(): string | null {
  // `expo-constants` exposes the Metro bundler URL as `hostUri` on Expo
  // Go / EAS dev builds. Shape: "192.168.1.42:8081" — strip port.
  const hostUri =
    Constants.expoConfig?.hostUri ??
    Constants.manifest2?.extra?.expoGo?.debuggerHost ??
    null;
  if (!hostUri) return null;
  const host = String(hostUri).split(":")[0];
  return host ? `http://${host}:8000` : null;
}

export const API_BASE_URL: string =
  process.env.EXPO_PUBLIC_API_URL ??
  guessDevHostUri() ??
  "http://localhost:8000";

export const API_PREFIX = "/api/v1";

export const api = (path: string): string =>
  `${API_BASE_URL}${API_PREFIX}${path.startsWith("/") ? path : `/${path}`}`;
