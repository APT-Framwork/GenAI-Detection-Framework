import * as Notifications from "expo-notifications";

/**
 * Local (on-device) notifications. These do NOT require an Expo push token
 * or an EAS projectId and work in Expo Go — handy for surfacing live SSE
 * alerts as system-tray pings while the user runs a dev build.
 *
 * For real background/killed-app push, the device still needs to register
 * with the backend via `usePushNotifications.ts` and receive Expo Push
 * messages (which Expo relays to FCM/APNs); local notifications only fire
 * while the app's JS runtime is alive.
 */

export type LocalAlert = {
  title: string;
  body: string;
  data?: Record<string, unknown>;
  /** "default" plays the OS notification sound; null is silent. */
  sound?: "default" | null;
};

/**
 * Fire a local notification immediately. Despite the name, we use a null
 * trigger (vs. a TIME_INTERVAL trigger) so the OS posts it on the next
 * tick — iOS rejects 0-second intervals.
 */
export async function presentLocalAlert(alert: LocalAlert): Promise<void> {
  await Notifications.scheduleNotificationAsync({
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
