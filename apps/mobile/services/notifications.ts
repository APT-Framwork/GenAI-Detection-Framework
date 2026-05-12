/**
 * Notifications service — gated so it's safe to import in Expo Go.
 *
 * On Android Expo Go SDK 53+, `expo-notifications` throws a hard error at
 * import time because the native module was removed. We detect Expo Go
 * with `Constants.executionEnvironment` and lazily resolve the module
 * only outside Expo Go. In Expo Go, every export becomes a no-op so the
 * rest of the app keeps booting.
 *
 * For real push notifications you need to be running a dev build /
 * standalone build — see the EAS dev build flow.
 */

import Constants from "expo-constants";

export type LocalAlert = {
  title: string;
  body: string;
  data?: Record<string, unknown>;
  sound?: "default" | null;
};

export const IS_EXPO_GO =
  Constants.executionEnvironment === "storeClient";

let _notifications: typeof import("expo-notifications") | null = null;
let _warned = false;

function getNotifications(): typeof import("expo-notifications") | null {
  if (IS_EXPO_GO) {
    if (!_warned) {
      _warned = true;
      console.info(
        "[notifications] running in Expo Go — system notifications disabled. Install the dev build to enable.",
      );
    }
    return null;
  }
  if (_notifications) return _notifications;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    _notifications = require("expo-notifications");
    return _notifications;
  } catch (err) {
    console.warn("[notifications] failed to load expo-notifications:", err);
    return null;
  }
}

export async function presentLocalAlert(alert: LocalAlert): Promise<void> {
  const N = getNotifications();
  if (!N) return;
  await N.scheduleNotificationAsync({
    content: {
      title: alert.title,
      body: alert.body,
      sound: alert.sound ?? "default",
      data: alert.data ?? { type: "alert" },
    },
    trigger: null,
  });
}

export async function scheduleCriticalAlert(
  title: string,
  body: string,
  data?: Record<string, unknown>,
): Promise<void> {
  await presentLocalAlert({
    title: `[CRITICAL] ${title}`,
    body,
    data: { type: "intervention", ...(data ?? {}) },
  });
}

/** Lazy accessor for callers that need the raw API (listeners, etc.). */
export function tryGetNotifications():
  | typeof import("expo-notifications")
  | null {
  return getNotifications();
}
