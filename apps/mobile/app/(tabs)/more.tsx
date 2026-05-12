/**
 * More — secondary surfaces that aren't primary SOC actions. Surfaces
 * the live feed (SSE), IOC search/threat intel, model health, and
 * profile.
 *
 * Each row deep-links to the existing screen (which remains a tab route
 * but is hidden from the tab bar via `href: null` in _layout.tsx).
 */

import { useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { typography, spacing, radius, shadows } from "../../lib/theme";
import { useColors } from "../../lib/theme-hook";
import { useUserStore } from "../../stores/user-store";

type Row = {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  caption: string;
  href: string;
};

export default function MoreScreen() {
  const router = useRouter();
  const c = useColors();
  const user = useUserStore((s) => s.user);
  const logout = useUserStore((s) => s.logout);

  const sections: { title: string; rows: Row[] }[] = [
    {
      title: "Operations",
      rows: [
        {
          icon: "shield-checkmark-outline",
          label: "Actions queue",
          caption: "Approve or decline pending DQN actions",
          href: "/(tabs)/actions",
        },
        {
          icon: "pulse-outline",
          label: "Live feed",
          caption: "Real-time SSE stream of every detection",
          href: "/(tabs)/feed",
        },
        {
          icon: "search-outline",
          label: "Threat intel search",
          caption: "Lookup IOCs and scan files with VirusTotal",
          href: "/(tabs)/search",
        },
        {
          icon: "speedometer-outline",
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
    <SafeAreaView style={[styles.container, { backgroundColor: c.bg }]} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.header}>
          <Text style={[styles.eyebrow, { color: c.textMuted }]}>UTILITIES</Text>
          <Text style={[styles.title, { color: c.textPrimary }]}>More</Text>
        </View>

        {sections.map((section) => (
          <View key={section.title} style={styles.section}>
            <Text style={[styles.sectionTitle, { color: c.textMuted }]}>
              {section.title}
            </Text>
            <View style={[styles.sectionCard, { backgroundColor: c.bgCard }]}>
              {section.rows.map((row, idx) => (
                <Pressable
                  key={row.label}
                  style={[
                    styles.row,
                    idx < section.rows.length - 1 && {
                      borderBottomWidth: 1,
                      borderBottomColor: c.border,
                    },
                  ]}
                  onPress={() => router.push(row.href as never)}
                >
                  <View
                    style={[styles.rowIcon, { backgroundColor: c.primaryLight }]}
                  >
                    <Ionicons name={row.icon} size={20} color={c.primary} />
                  </View>
                  <View style={styles.rowText}>
                    <Text style={[styles.rowLabel, { color: c.textPrimary }]}>
                      {row.label}
                    </Text>
                    <Text
                      style={[styles.rowCaption, { color: c.textMuted }]}
                      numberOfLines={1}
                    >
                      {row.caption}
                    </Text>
                  </View>
                  <Ionicons
                    name="chevron-forward"
                    size={16}
                    color={c.textMuted}
                  />
                </Pressable>
              ))}
            </View>
          </View>
        ))}

        <Pressable
          style={[
            styles.signOutBtn,
            { borderColor: c.critical, backgroundColor: c.criticalBg },
          ]}
          onPress={() => logout()}
        >
          <Ionicons name="log-out-outline" size={16} color={c.critical} />
          <Text style={[styles.signOutText, { color: c.critical }]}>
            SIGN OUT
          </Text>
        </Pressable>

        <Text style={[styles.versionLine, { color: c.textMuted }]}>
          CAVIX · Powered by STRIX RL · v1.0.0
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
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
    letterSpacing: typography.tracking.widest,
  },
  title: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["3xl"],
    letterSpacing: typography.tracking.tight,
  },
  section: { paddingHorizontal: spacing.md, marginBottom: spacing.lg },
  sectionTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    letterSpacing: typography.tracking.widest,
    marginBottom: spacing.sm,
  },
  sectionCard: {
    borderRadius: radius.md,
    ...shadows.card,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
  },
  rowIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  rowText: { flex: 1, gap: 2 },
  rowLabel: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
  },
  rowCaption: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xs,
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
  },
  signOutText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    letterSpacing: typography.tracking.wider,
  },
  versionLine: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    textAlign: "center",
    marginTop: spacing.lg,
    letterSpacing: typography.tracking.wide,
  },
});
