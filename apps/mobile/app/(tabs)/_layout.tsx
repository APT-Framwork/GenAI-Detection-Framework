import { Tabs } from "expo-router";
import { View, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, typography, radius, spacing } from "../../lib/theme";
import { useUnacknowledgedCount } from "../../lib/api/hooks";

type TabIcon = React.ComponentProps<typeof Ionicons>["name"];

const TAB_CONFIG: {
  name: string;
  title: string;
  icon: TabIcon;
  iconActive: TabIcon;
}[] = [
  { name: "dashboard", title: "DASHBOARD", icon: "grid-outline", iconActive: "grid" },
  { name: "alerts", title: "ALERTS", icon: "notifications-outline", iconActive: "notifications" },
  { name: "search", title: "SEARCH", icon: "search-outline", iconActive: "search" },
  { name: "status", title: "NETWORK", icon: "globe-outline", iconActive: "globe" },
  { name: "profile", title: "SETTINGS", icon: "settings-outline", iconActive: "settings" },
];

export default function TabLayout() {
  const unackQ = useUnacknowledgedCount();
  const unreadCount = unackQ.data?.count ?? 0;

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
      {TAB_CONFIG.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarIcon: ({ focused, color }) => (
              <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
                <Ionicons
                  name={focused ? tab.iconActive : tab.icon}
                  size={20}
                  color={focused ? colors.tabActive : colors.tabInactive}
                />
              </View>
            ),
            tabBarBadge:
              tab.name === "alerts" && unreadCount > 0
                ? unreadCount
                : undefined,
            tabBarBadgeStyle: styles.badge,
          }}
        />
      ))}
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: "rgba(255,255,255,0.7)",
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
    paddingHorizontal: 20,
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
