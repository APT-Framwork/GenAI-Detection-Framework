import { Stack } from "expo-router";

export default function OnboardingLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        animation: "slide_from_right",
      }}
    >
      <Stack.Screen name="detection" />
      <Stack.Screen name="intelligence" />
      <Stack.Screen name="orchestration" />
    </Stack>
  );
}
