import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";
import { mockUser } from "../../lib/mock-data";
import { useUIStore } from "../../stores/ui-store";

type SettingsItem = {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  value?: string;
  danger?: boolean;
};

const SETTINGS_SECTIONS: { title: string; items: SettingsItem[] }[] = [
  {
    title: "PREFERENCES",
    items: [
      { icon: "moon-outline", label: "Dark Mode", value: "Off" },
      { icon: "notifications-outline", label: "Push Notifications", value: "On" },
      { icon: "finger-print-outline", label: "Biometric Lock", value: "Off" },
      { icon: "language-outline", label: "Language", value: "English" },
    ],
  },
  {
    title: "SYSTEM",
    items: [
      { icon: "cloud-download-outline", label: "Data Sync", value: "Auto" },
      { icon: "server-outline", label: "API Endpoint", value: "Production" },
      { icon: "document-text-outline", label: "Logs", value: "Verbose" },
    ],
  },
  {
    title: "ACCOUNT",
    items: [
      { icon: "shield-checkmark-outline", label: "Security Settings" },
      { icon: "help-circle-outline", label: "Help & Support" },
      { icon: "log-out-outline", label: "Sign Out", danger: true },
    ],
  },
];

export default function ProfileScreen() {
  const isDark = useUIStore((s) => s.isDark);

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Settings</Text>
        </View>

        {/* Profile card */}
        <View style={styles.profileCard}>
          <View style={styles.avatarLarge}>
            <Text style={styles.avatarText}>
              {mockUser.name
                .split(" ")
                .map((n) => n[0])
                .join("")}
            </Text>
          </View>
          <View style={styles.profileInfo}>
            <Text style={styles.profileName}>{mockUser.name}</Text>
            <Text style={styles.profileRole}>{mockUser.role}</Text>
            <Text style={styles.profileDesignation}>
              {mockUser.designation}
            </Text>
          </View>
        </View>

        {/* Stats row */}
        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{mockUser.efficiency}%</Text>
            <Text style={styles.statLabel}>EFFICIENCY</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{mockUser.accuracy}%</Text>
            <Text style={styles.statLabel}>ACCURACY</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{mockUser.responseTime}</Text>
            <Text style={styles.statLabel}>RESPONSE</Text>
          </View>
        </View>

        {/* Settings sections */}
        {SETTINGS_SECTIONS.map((section) => (
          <View key={section.title} style={styles.section}>
            <Text style={styles.sectionTitle}>{section.title}</Text>
            <View style={styles.sectionCard}>
              {section.items.map((item, idx) => (
                <Pressable
                  key={item.label}
                  style={[
                    styles.settingsRow,
                    idx < section.items.length - 1 && styles.settingsRowBorder,
                  ]}
                >
                  <Ionicons
                    name={item.icon}
                    size={20}
                    color={item.danger ? colors.critical : colors.textMuted}
                  />
                  <Text
                    style={[
                      styles.settingsLabel,
                      item.danger && { color: colors.critical },
                    ]}
                  >
                    {item.label}
                  </Text>
                  {item.value ? (
                    <Text style={styles.settingsValue}>{item.value}</Text>
                  ) : (
                    <Ionicons
                      name="chevron-forward"
                      size={16}
                      color={item.danger ? colors.critical : colors.textLight}
                    />
                  )}
                </Pressable>
              ))}
            </View>
          </View>
        ))}

        {/* Version */}
        <Text style={styles.version}>STRIX v1.0.0 — Sentinel Engine 4.2.0</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  scroll: {
    paddingBottom: spacing["3xl"],
  },
  header: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  headerTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["4xl"],
    color: colors.textPrimary,
    letterSpacing: typography.tracking.tight,
  },
  profileCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginHorizontal: spacing.lg,
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.lg,
    ...shadows.card,
  },
  avatarLarge: {
    width: 56,
    height: 56,
    borderRadius: radius.full,
    backgroundColor: colors.bgAccent,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["2xl"],
    color: colors.primary,
  },
  profileInfo: {
    flex: 1,
    gap: 2,
  },
  profileName: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.textPrimary,
  },
  profileRole: {
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textBody,
  },
  profileDesignation: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: 0.5,
  },
  statsRow: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.md,
    ...shadows.card,
  },
  statItem: {
    flex: 1,
    alignItems: "center",
    gap: 2,
  },
  statValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.textPrimary,
  },
  statLabel: {
    fontFamily: typography.family.heading,
    fontSize: 8,
    color: colors.textMuted,
    letterSpacing: 0.5,
  },
  statDivider: {
    width: 1,
    height: 32,
    backgroundColor: colors.border,
  },
  section: {
    marginTop: spacing.lg,
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
  },
  sectionTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: 1,
  },
  sectionCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    ...shadows.card,
  },
  settingsRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
  },
  settingsRowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  settingsLabel: {
    flex: 1,
    fontFamily: typography.family.bodyMedium,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  settingsValue: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  version: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textLight,
    textAlign: "center",
    marginTop: spacing.xl,
    letterSpacing: 0.5,
  },
});
