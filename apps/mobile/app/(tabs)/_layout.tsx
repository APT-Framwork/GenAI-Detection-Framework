import { Tabs } from "expo-router";
import { View, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { typography, radius } from "../../lib/theme";
import { useColors } from "../../lib/theme-hook";
import { useUnacknowledgedCount, useActions, useCases } from "../../lib/api/hooks";

type TabIcon = React.ComponentProps<typeof Ionicons>["name"];

const PRIMARY_TABS: {
  name: string;
  title: string;
  icon: TabIcon;
  iconActive: TabIcon;
}[] = [
  { name: "dashboard", title: "HOME",     icon: "grid-outline",         iconActive: "grid" },
  { name: "alerts",    title: "ALERTS",   icon: "notifications-outline", iconActive: "notifications" },
  { name: "cases",     title: "CASES",    icon: "briefcase-outline",    iconActive: "briefcase" },
  { name: "actions",   title: "ACTIONS",  icon: "shield-checkmark-outline", iconActive: "shield-checkmark" },
  { name: "more",      title: "MORE",     icon: "ellipsis-horizontal-circle-outline", iconActive: "ellipsis-horizontal-circle" },
];

// Secondary routes still inside (tabs)/ but hidden from the bar — reachable
// via deep link or the More hub.
const HIDDEN_ROUTES = ["feed", "search", "status", "profile"] as const;

export default function TabLayout() {
  const colors = useColors();
  const unackQ = useUnacknowledgedCount();
  const actionsQ = useActions("pending");
  const casesQ = useCases({ status: "new" });

  const alertsUnread = unackQ.data?.count ?? 0;
  const pendingActions = actionsQ.data?.counts?.proposed ?? 0;
  const newCases = casesQ.data?.counts?.new ?? 0;

  const badgeFor = (name: string): number | undefined => {
    if (name === "alerts" && alertsUnread > 0) return alertsUnread;
    if (name === "cases" && newCases > 0) return newCases;
    if (name === "actions" && pendingActions > 0) return pendingActions;
    // The More tab no longer surfaces a count — too noisy now that
    // Alerts is a primary tab carrying its own badge.
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
      }}
    >
      {PRIMARY_TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarIcon: ({ focused }) => (
              <View
                style={[
                  styles.iconWrap,
                  focused && { backgroundColor: colors.tabActiveBg },
                ]}
              >
                <Ionicons
                  name={focused ? tab.iconActive : tab.icon}
                  size={20}
                  color={focused ? colors.tabActive : colors.tabInactive}
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
    height: 88,
    paddingTop: 8,
    paddingBottom: 24,
    shadowColor: "#00343d",
    shadowOffset: { width: 0, height: -12 },
    shadowOpacity: 0.06,
    shadowRadius: 32,
    elevation: 10,
  },
  tabLabel: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    letterSpacing: 1,
    textTransform: "uppercase",
    marginTop: 4,
  },
  iconWrap: {
    paddingHorizontal: 16,
    paddingVertical: 4,
    borderRadius: radius.md,
  },
  badge: {
    fontSize: 10,
    fontFamily: typography.family.heading,
    minWidth: 18,
    height: 18,
    lineHeight: 18,
  },
});
