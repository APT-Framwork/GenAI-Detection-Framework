/**
 * More — secondary surfaces that aren't primary SOC actions. Surfaces
 * alert history, IOC search/threat intel, model health, and profile.
 *
 * Each row deep-links to the existing screen (which remains a tab route
 * but is hidden from the tab bar via `href: null` in _layout.tsx).
 */

import { useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, shadows, spacing, typography } from "../../lib/theme";
import { useUnacknowledgedCount } from "../../lib/api/hooks";
import { useUserStore } from "../../stores/user-store";

type Row = {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  caption: string;
  href: string;
  badge?: number;
};

export default function MoreScreen() {
  const router = useRouter();
  const unackQ = useUnacknowledgedCount();
  const user = useUserStore((s) => s.user);
  const logout = useUserStore((s) => s.logout);
  const unread = unackQ.data?.count ?? 0;

  const sections: { title: string; rows: Row[] }[] = [
    {
      title: "Operations",
      rows: [
        {
          icon: "notifications-outline",
          label: "Alert log",
          caption: "Acknowledge and review every detection",
          href: "/(tabs)/alerts",
          badge: unread,
        },
        {
          icon: "search-outline",
          label: "Threat intel search",
          caption: "Lookup IOCs and scan files with VirusTotal",
          href: "/(tabs)/search",
        },
        {
          icon: "pulse-outline",
          label: "Model health",
          caption: "Drift, accuracy, and latency per model",
          href: "/(tabs)/status",
        },
      ],
    },
    {
      title: "Account",
      rows: [
        {
          icon: "person-outline",
          label: "Profile & settings",
          caption: user?.email ?? "Manage your account",
          href: "/(tabs)/profile",
        },
      ],
    },
  ];

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.header}>
          <Text style={styles.eyebrow}>UTILITIES</Text>
          <Text style={styles.title}>More</Text>
        </View>

        {sections.map((section) => (
          <View key={section.title} style={styles.section}>
            <Text style={styles.sectionTitle}>{section.title}</Text>
            <View style={styles.sectionCard}>
              {section.rows.map((row, idx) => (
                <Pressable
                  key={row.label}
                  style={[
                    styles.row,
                    idx < section.rows.length - 1 && styles.rowBorder,
                  ]}
                  onPress={() => router.push(row.href as never)}
                >
                  <View style={styles.rowIcon}>
                    <Ionicons name={row.icon} size={20} color={colors.primary} />
                  </View>
                  <View style={styles.rowText}>
                    <Text style={styles.rowLabel}>{row.label}</Text>
                    <Text style={styles.rowCaption} numberOfLines={1}>
                      {row.caption}
                    </Text>
                  </View>
                  {row.badge && row.badge > 0 ? (
                    <View style={styles.badge}>
                      <Text style={styles.badgeText}>{row.badge}</Text>
                    </View>
                  ) : null}
                  <Ionicons
                    name="chevron-forward"
                    size={16}
                    color={colors.textMuted}
                  />
                </Pressable>
              ))}
            </View>
          </View>
        ))}

        <Pressable style={styles.signOutBtn} onPress={() => logout()}>
          <Ionicons name="log-out-outline" size={16} color={colors.critical} />
          <Text style={styles.signOutText}>SIGN OUT</Text>
        </Pressable>

        <Text style={styles.versionLine}>
          CAVIX · Powered by STRIX RL · v1.0.0
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { paddingBottom: spacing["2xl"] },
  header: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    gap: 2,
  },
  eyebrow: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: typography.tracking.widest,
  },
  title: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["3xl"],
    color: colors.textPrimary,
    letterSpacing: typography.tracking.tight,
  },
  section: { paddingHorizontal: spacing.md, marginBottom: spacing.lg },
  sectionTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: typography.tracking.widest,
    marginBottom: spacing.sm,
  },
  sectionCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    ...shadows.card,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  rowIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.primaryLight,
    alignItems: "center",
    justifyContent: "center",
  },
  rowText: { flex: 1, gap: 2 },
  rowLabel: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  rowCaption: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  badge: {
    minWidth: 22,
    height: 20,
    paddingHorizontal: 6,
    borderRadius: 10,
    backgroundColor: colors.critical,
    alignItems: "center",
    justifyContent: "center",
  },
  badgeText: {
    fontFamily: typography.family.heading,
    fontSize: 10,
    color: colors.white,
  },
  signOutBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    marginHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.critical,
    backgroundColor: colors.criticalBg,
  },
  signOutText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.critical,
    letterSpacing: typography.tracking.wider,
  },
  versionLine: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    textAlign: "center",
    marginTop: spacing.lg,
    letterSpacing: typography.tracking.wide,
  },
});
