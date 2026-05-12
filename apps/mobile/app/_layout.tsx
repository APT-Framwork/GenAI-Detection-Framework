import { useEffect, useCallback } from "react";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useFonts } from "expo-font";
import {
  SpaceGrotesk_700Bold,
  SpaceGrotesk_500Medium,
  SpaceGrotesk_400Regular,
  SpaceGrotesk_300Light,
  SpaceGrotesk_600SemiBold,
} from "@expo-google-fonts/space-grotesk";
import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
} from "@expo-google-fonts/inter";
import { Ionicons } from "@expo/vector-icons";
import * as SplashScreen from "expo-splash-screen";

import { ErrorBoundary } from "../components/ErrorBoundary";
import { QueryProvider } from "../lib/api/QueryProvider";
import { usePushNotifications } from "../hooks/usePushNotifications";
import { useLocalAlertPings } from "../hooks/useLocalAlertPings";
import { useUIStore } from "../stores/ui-store";
import { useUserStore } from "../stores/user-store";

SplashScreen.preventAutoHideAsync();

/**
 * Root layout. Responsibilities:
 *  - Load fonts before showing any UI.
 *  - Bootstrap the auth store once on cold start (reads SecureStore +
 *    validates via /auth/me).
 *  - Redirect based on auth status:
 *      booting → stay on the current screen (splash / index)
 *      anon    → force to /(auth)/login, unless already in the splash
 *                / onboarding flow
 *      authed  → if currently in (auth), bounce to /(tabs)/dashboard
 */
export default function RootLayout() {
  const [fontsLoaded] = useFonts({
    "SpaceGrotesk-Bold": SpaceGrotesk_700Bold,
    "SpaceGrotesk-SemiBold": SpaceGrotesk_600SemiBold,
    "SpaceGrotesk-Medium": SpaceGrotesk_500Medium,
    "SpaceGrotesk-Regular": SpaceGrotesk_400Regular,
    "SpaceGrotesk-Light": SpaceGrotesk_300Light,
    "Inter-Regular": Inter_400Regular,
    "Inter-Medium": Inter_500Medium,
    "Inter-SemiBold": Inter_600SemiBold,
    // Ship the Ionicons glyph font with the JS bundle — Expo Go on iOS
    // doesn't auto-load it for SDK 54, so tab-bar icons rendered blank
    // until this entry existed.
    ...Ionicons.font,
  });

  const bootstrap = useUserStore((s) => s.bootstrap);
  const hydratePrefs = useUIStore((s) => s.hydrate);
  const status = useUserStore((s) => s.status);
  const router = useRouter();
  const segments = useSegments();

  // Kick off auth + UI hydration once fonts are ready.
  useEffect(() => {
    if (fontsLoaded) {
      void bootstrap();
      void hydratePrefs();
    }
  }, [fontsLoaded, bootstrap, hydratePrefs]);

  // Hide the native splash once fonts are up — our own /index.tsx
  // handles the branded splash animation.
  const onLayoutRootView = useCallback(async () => {
    if (fontsLoaded) {
      await SplashScreen.hideAsync();
    }
  }, [fontsLoaded]);

  useEffect(() => {
    onLayoutRootView();
  }, [onLayoutRootView]);

  // ---- auth-gated routing ------------------------------------------
  useEffect(() => {
    if (!fontsLoaded || status === "booting") return;

    const inAuthGroup = segments[0] === "(auth)";
    const inTabs = segments[0] === "(tabs)";
    const inAnalysis = segments[0] === "analysis";

    if (status === "anon" && (inTabs || inAnalysis)) {
      router.replace("/(auth)/login");
    } else if (status === "authed" && inAuthGroup) {
      router.replace("/(tabs)/dashboard");
    }
  }, [status, segments, fontsLoaded, router]);

  if (!fontsLoaded) return null;

  return (
    <ErrorBoundary>
      <QueryProvider>
        <ThemedStatusBar />
        <AppShell />
      </QueryProvider>
    </ErrorBoundary>
  );
}

function ThemedStatusBar() {
  const isDark = useUIStore((s) => s.isDark);
  return <StatusBar style={isDark ? "light" : "dark"} />;
}

/**
 * Renders the route stack and wires post-auth side effects. Must live
 * below `<QueryProvider>` + inside the Expo Router tree so hooks that
 * depend on either (push registration, router, etc) can resolve.
 */
function AppShell() {
  usePushNotifications();
  useLocalAlertPings();
  return (
    <Stack screenOptions={{ headerShown: false, animation: "fade" }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(onboarding)" />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="analysis/[id]" options={{ animation: "slide_from_right" }} />
    </Stack>
  );
}
