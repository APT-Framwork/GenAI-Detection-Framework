import { useEffect, useRef } from "react";
import { Platform } from "react-native";
import Constants from "expo-constants";
import * as Device from "expo-device";
import { useRouter } from "expo-router";

import { registerDevice, unregisterDevice } from "../lib/api/auth";
import { useUserStore } from "../stores/user-store";
import { IS_EXPO_GO, tryGetNotifications } from "../services/notifications";

/**
 * Mobile push setup — called once in the root layout.
 *
 * In Expo Go on Android (SDK 53+) the underlying `expo-notifications`
 * module throws at import time, so we go through `tryGetNotifications`
 * which returns null when running in Expo Go. The hook becomes a no-op
 * there. In a dev/standalone build it behaves as before:
 *
 *   1. Configures how notifications render in foreground.
 *   2. Registers the device with the backend the moment we go
 *      `status === "authed"`. Unregister on the transition to `anon`.
 *   3. Routes taps → if the payload carries `chainId`, deep-link to the
 *      chain analysis screen.
 */

(() => {
  const N = tryGetNotifications();
  if (!N) return;
  N.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: true,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });
})();

const TOKEN_REF = { current: null as string | null };
const WARNED_NO_PROJECT_ID = { current: false };

type RemoveFn = { remove: () => void };

export function usePushNotifications() {
  const status = useUserStore((s) => s.status);
  const router = useRouter();

  const notificationListener = useRef<RemoveFn | null>(null);
  const responseListener = useRef<RemoveFn | null>(null);

  // Set up OS-level listeners once. No-op in Expo Go.
  useEffect(() => {
    const N = tryGetNotifications();
    if (!N) return;

    notificationListener.current = N.addNotificationReceivedListener(() => {});

    responseListener.current = N.addNotificationResponseReceivedListener(
      (resp) => {
        const data = resp.notification.request.content.data as
          | { type?: string; chainId?: string }
          | undefined;
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
    if (IS_EXPO_GO) return;

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
  const N = tryGetNotifications();
  if (!N) return null;
  if (!Device.isDevice) return null;

  const { status: existingStatus } = await N.getPermissionsAsync();
  let finalStatus = existingStatus;
  if (existingStatus !== "granted") {
    const { status } = await N.requestPermissionsAsync();
    finalStatus = status;
  }
  if (finalStatus !== "granted") return null;

  if (Platform.OS === "android") {
    await N.setNotificationChannelAsync("default", {
      name: "default",
      importance: N.AndroidImportance.MAX,
    });
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ??
    Constants.easConfig?.projectId ??
    null;

  if (!projectId) {
    if (!WARNED_NO_PROJECT_ID.current) {
      WARNED_NO_PROJECT_ID.current = true;
      console.info(
        "[push] No EAS projectId — backgrounded push disabled. Run `eas init` and add expo.extra.eas.projectId in app.json.",
      );
    }
    return null;
  }

  try {
    const token = await N.getExpoPushTokenAsync({ projectId });
    console.log("[push] got Expo push token, registering with API");
    return token.data;
  } catch (err) {
    console.warn("[push] getExpoPushTokenAsync failed:", err);
    return null;
  }
}
