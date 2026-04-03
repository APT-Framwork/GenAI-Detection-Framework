import { useEffect, useCallback } from "react";
import { Stack } from "expo-router";
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
import * as SplashScreen from "expo-splash-screen";

SplashScreen.preventAutoHideAsync();

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
  });

  const onLayoutRootView = useCallback(async () => {
    if (fontsLoaded) {
      await SplashScreen.hideAsync();
    }
  }, [fontsLoaded]);

  useEffect(() => {
    onLayoutRootView();
  }, [onLayoutRootView]);

  if (!fontsLoaded) return null;

  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false, animation: "fade" }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="(onboarding)" />
        <Stack.Screen name="(tabs)" />
      </Stack>
    </>
  );
}
