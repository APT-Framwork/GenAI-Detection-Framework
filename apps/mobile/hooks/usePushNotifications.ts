import { useEffect, useRef } from "react";
import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import * as Device from "expo-device";
import Constants from "expo-constants";
import { type EventSubscription } from "expo-modules-core";
import { useRouter } from "expo-router";

import { registerDevice, unregisterDevice } from "../lib/api/auth";
import { useUserStore } from "../stores/user-store";

/**
 * Mobile push setup — called once in the root layout.
 *
 *   1. Configures how notifications render in foreground.
 *   2. Registers the device with the backend the moment we go
 *      `status === "authed"` (so the Expo push token lives alongside
 *      the fresh access token). Unregister on the transition to
 *      `anon`.
 *   3. Routes taps → if the notification payload carries `chainId`,
 *      deep-link the user straight to that chain analysis.
 */

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

const TOKEN_REF = { current: null as string | null };
const WARNED_NO_PROJECT_ID = { current: false };

export function usePushNotifications() {
  const status = useUserStore((s) => s.status);
  const router = useRouter();

  const notificationListener = useRef<EventSubscription | null>(null);
  const responseListener = useRef<EventSubscription | null>(null);

  // Set up OS-level listeners once.
  useEffect(() => {
    notificationListener.current =
      Notifications.addNotificationReceivedListener(() => {});

    responseListener.current = Notifications.addNotificationResponseReceivedListener(
      (resp) => {
        const data = resp.notification.request.content.data as {
          type?: string;
          chainId?: string;
        } | undefined;
        if (data?.type === "intervention" && data.chainId) {
          router.push({
            pathname: "/analysis/[id]",
            params: { id: String(data.chainId) },
          });
        }
      },
    );

    return () => {
      notificationListener.current?.remove();
      responseListener.current?.remove();
    };
  }, [router]);

  // Register / unregister when auth status flips.
  useEffect(() => {
    let cancelled = false;

    async function register() {
      const token = await getExpoPushToken();
      if (!token || cancelled) return;
      TOKEN_REF.current = token;
      const platform: "ios" | "android" | "web" =
        Platform.OS === "ios" || Platform.OS === "android"
          ? Platform.OS
          : "web";
      await registerDevice({
        expoPushToken: token,
        platform,
        appVersion: Constants.expoConfig?.version ?? "1.0.0",
      });
    }

    async function unregister() {
      const token = TOKEN_REF.current;
      TOKEN_REF.current = null;
      if (token) await unregisterDevice(token);
    }

    if (status === "authed") {
      void register();
    } else if (status === "anon") {
      void unregister();
    }

    return () => {
      cancelled = true;
    };
  }, [status]);
}

async function getExpoPushToken(): Promise<string | null> {
  if (!Device.isDevice) return null;

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;
  if (existingStatus !== "granted") {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }
  if (finalStatus !== "granted") return null;

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "default",
      importance: Notifications.AndroidImportance.MAX,
    });
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ??
    Constants.easConfig?.projectId ??
    null;

  if (!projectId) {
    // Expo Go on SDK 54 requires an EAS projectId — without it the
    // push token request silently fails and the device never registers
    // with the backend. Log loudly so the operator can fix app.json
    // (`expo.extra.eas.projectId`) instead of wondering why
    // notifications never arrive.
    console.warn(
      "[push] No EAS projectId configured — push notifications will not work in Expo Go. " +
        "Set expo.extra.eas.projectId in app.json after running `eas init`.",
    );
    return null;
  }

  try {
    const token = await Notifications.getExpoPushTokenAsync({ projectId });
    console.log("[push] got Expo push token, registering with API");
    return token.data;
  } catch (err) {
    console.warn("[push] getExpoPushTokenAsync failed:", err);
    return null;
  }
}
