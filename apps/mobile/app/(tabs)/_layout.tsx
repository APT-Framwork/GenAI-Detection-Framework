import { Tabs } from "expo-router";
import { View, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors, typography, radius } from "../../lib/theme";
import { useUnacknowledgedCount, useActions, useCases } from "../../lib/api/hooks";

type TabIcon = React.ComponentProps<typeof Ionicons>["name"];

const PRIMARY_TABS: {
  name: string;
  title: string;
  icon: TabIcon;
  iconActive: TabIcon;
}[] = [
  { name: "dashboard", title: "HOME",     icon: "grid-outline",         iconActive: "grid" },
  { name: "feed",      title: "FEED",     icon: "pulse-outline",        iconActive: "pulse" },
  { name: "cases",     title: "CASES",    icon: "briefcase-outline",    iconActive: "briefcase" },
  { name: "actions",   title: "ACTIONS",  icon: "shield-checkmark-outline", iconActive: "shield-checkmark" },
  { name: "more",      title: "MORE",     icon: "ellipsis-horizontal-circle-outline", iconActive: "ellipsis-horizontal-circle" },
];

// Secondary routes still in (tabs)/ but hidden from the bar.
const HIDDEN_ROUTES = ["alerts", "search", "status", "profile"] as const;

export default function TabLayout() {
  // Three queries drive tab badges — kept lightweight; React Query
  // dedupes them with the screens that use the same keys.
  const unackQ = useUnacknowledgedCount();
  const actionsQ = useActions("pending");
  const casesQ = useCases({ status: "new" });

  const alertsUnread = unackQ.data?.count ?? 0;
  const pendingActions = actionsQ.data?.counts?.pending ?? 0;
  const newCases = casesQ.data?.counts?.new ?? 0;

  const badgeFor = (name: string): number | undefined => {
    if (name === "actions" && pendingActions > 0) return pendingActions;
    if (name === "cases" && newCases > 0) return newCases;
    if (name === "more" && alertsUnread > 0) return alertsUnread;
    return undefined;
  };

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: styles.tabBar,
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
              <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
                <Ionicons
                  name={focused ? tab.iconActive : tab.icon}
                  size={20}
                  color={focused ? colors.tabActive : colors.tabInactive}
                />
              </View>
            ),
            tabBarBadge: badgeFor(tab.name),
            tabBarBadgeStyle: styles.badge,
          }}
        />
      ))}

      {HIDDEN_ROUTES.map((name) => (
        <Tabs.Screen
          key={name}
          name={name}
          // `href: null` keeps the route resolvable for deep links but
          // omits it from the tab bar — accessed via the More screen.
          options={{ href: null }}
        />
      ))}
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: "rgba(255,255,255,0.92)",
    borderTopWidth: 1,
    borderTopColor: colors.border,
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
  iconWrapActive: {
    backgroundColor: colors.tabActiveBg,
    borderRadius: radius.md,
  },
  badge: {
    backgroundColor: colors.critical,
    fontSize: 10,
    fontFamily: typography.family.heading,
    minWidth: 18,
    height: 18,
    lineHeight: 18,
  },
});
