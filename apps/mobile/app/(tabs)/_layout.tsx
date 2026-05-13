import { useEffect, useState } from "react";
import { Tabs } from "expo-router";
import { View, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Font from "expo-font";

import { typography } from "../../lib/theme";
import { useColors } from "../../lib/theme-hook";
import { useUnacknowledgedCount, useCases } from "../../lib/api/hooks";
import { useUIStore } from "../../stores/ui-store";

type TabIcon = React.ComponentProps<typeof Ionicons>["name"];

const PRIMARY_TABS: {
  name: string;
  title: string;
  icon: TabIcon;
  iconActive: TabIcon;
  /** Unicode fallback rendered if the Ionicons glyph font isn't ready
   * (Expo Go on iOS SDK 54 with the new architecture occasionally fails
   * to register the font even after `useFonts` resolves). The emoji
   * always renders via the system Apple Color Emoji font, so the bar
   * never goes blank. */
  fallback: string;
}[] = [
  { name: "dashboard", title: "HOME",   icon: "grid-outline",                       iconActive: "grid",                       fallback: "🏠" },
  { name: "alerts",    title: "ALERTS", icon: "notifications-outline",              iconActive: "notifications",              fallback: "🔔" },
  { name: "cases",     title: "CASES",  icon: "briefcase-outline",                  iconActive: "briefcase",                  fallback: "📂" },
  { name: "more",      title: "MORE",   icon: "ellipsis-horizontal-circle-outline", iconActive: "ellipsis-horizontal-circle", fallback: "⋯" },
];

// Secondary routes still inside (tabs)/ but hidden from the bar — reachable
// via deep link or the More hub.
const HIDDEN_ROUTES = ["actions", "feed", "search", "status", "profile"] as const;

export default function TabLayout() {
  const colors = useColors();
  const unackQ = useUnacknowledgedCount();
  const casesQ = useCases({ status: "new" });
  const alertsBadgeBaseline = useUIStore((s) => s.alertsBadgeBaseline);

  // Belt-and-braces font load — `useFonts` in the root layout *should* have
  // registered Ionicons already, but on Expo Go iOS SDK 54 + Fabric the
  // per-icon `Font.isLoaded('ionicons')` check has been observed to return
  // `false` at first render, leaving the tab bar blank. We re-load
  // imperatively here and flip `ionLoaded` so the bar re-renders.
  const [ionLoaded, setIonLoaded] = useState<boolean>(() =>
    Font.isLoaded("ionicons"),
  );
  useEffect(() => {
    if (ionLoaded) return;
    let cancelled = false;
    (async () => {
      try {
        await Ionicons.loadFont();
        if (!cancelled) setIonLoaded(true);
      } catch (err) {
        console.warn("[tabs] Ionicons.loadFont failed:", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ionLoaded]);

  const alertsUnread = Math.max(
    0,
    (unackQ.data?.count ?? 0) - alertsBadgeBaseline,
  );
  const newCases = casesQ.data?.counts?.new ?? 0;

  const badgeFor = (name: string): number | undefined => {
    if (name === "alerts" && alertsUnread > 0) return alertsUnread;
    if (name === "cases" && newCases > 0) return newCases;
    return undefined;
  };

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          ...styles.tabBar,
          backgroundColor: colors.tabBar,
          borderTopColor: colors.border,
        },
        tabBarActiveTintColor: colors.tabActive,
        tabBarInactiveTintColor: colors.tabInactive,
        tabBarLabelStyle: styles.tabLabel,
        tabBarIconStyle: styles.iconStyle,
        tabBarItemStyle: styles.itemStyle,
      }}
    >
      {PRIMARY_TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarIcon: ({ focused }) => (
              <View style={styles.iconCell}>
                {ionLoaded ? (
                  <Ionicons
                    name={focused ? tab.iconActive : tab.icon}
                    size={22}
                    color={focused ? colors.tabActive : colors.tabInactive}
                  />
                ) : (
                  <Text
                    style={[
                      styles.fallbackGlyph,
                      {
                        color: focused
                          ? colors.tabActive
                          : colors.tabInactive,
                      },
                    ]}
                  >
                    {tab.fallback}
                  </Text>
                )}
                <View
                  style={[
                    styles.activeDot,
                    {
                      backgroundColor: focused
                        ? colors.tabActive
                        : "transparent",
                    },
                  ]}
                />
              </View>
            ),
            tabBarBadge: badgeFor(tab.name),
            tabBarBadgeStyle: {
              ...styles.badge,
              backgroundColor: colors.critical,
              color: colors.white,
            },
          }}
        />
      ))}

      {HIDDEN_ROUTES.map((name) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{ href: null }}
        />
      ))}
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    borderTopWidth: 1,
    height: 86,
    paddingTop: 10,
    paddingBottom: 22,
    shadowColor: "#00343d",
    shadowOffset: { width: 0, height: -12 },
    shadowOpacity: 0.06,
    shadowRadius: 32,
    elevation: 10,
  },
  tabLabel: {
    fontFamily: typography.family.heading,
    fontSize: 10,
    letterSpacing: 1,
    textTransform: "uppercase",
    marginTop: 6,
  },
  itemStyle: {
    paddingTop: 6,
    paddingBottom: 0,
  },
  iconStyle: {
    // We render our own icon cell — disable the default 24px box so the
    // dot indicator sits flush under the glyph.
    marginTop: 0,
    marginBottom: 0,
    width: 28,
    height: 24,
  },
  iconCell: {
    alignItems: "center",
    justifyContent: "center",
    height: 24,
  },
  activeDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    marginTop: 3,
  },
  fallbackGlyph: {
    fontSize: 18,
    lineHeight: 22,
    textAlign: "center",
  },
  badge: {
    fontSize: 10,
    fontFamily: typography.family.heading,
    minWidth: 18,
    height: 18,
    lineHeight: 18,
  },
});
