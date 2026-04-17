import { View, Text, StyleSheet, ScrollView, Pressable, FlatList } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";
import { useAlertsStore } from "../../stores/alerts-store";
import { AlertCard } from "../../components/AlertCard";
import type { Severity } from "../../lib/mock-data";

const FILTERS: { key: Severity | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "critical", label: "Critical" },
  { key: "warning", label: "Warning" },
  { key: "info", label: "Info" },
  { key: "update", label: "Update" },
];

export default function AlertsScreen() {
  const { filter, setFilter, filteredAlerts, acknowledge, alerts } =
    useAlertsStore();

  const displayAlerts = filteredAlerts();
  const totalCount = alerts.length;

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={styles.logoIcon}>
            <View style={styles.logoPupil} />
          </View>
          <Text style={styles.headerTitle}>SENTINEL</Text>
        </View>
        <View style={styles.avatar} />
      </View>

      {/* Page title */}
      <View style={styles.titleSection}>
        <Text style={styles.subtitle}>LIVE SECURITY FEED</Text>
        <Text style={styles.title}>STRIX Notifications</Text>
      </View>

      {/* Filters */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filterScroll}
        contentContainerStyle={styles.filterRow}
      >
        {FILTERS.map((f) => (
          <Pressable
            key={f.key}
            style={[
              styles.filterChip,
              filter === f.key && styles.filterChipActive,
            ]}
            onPress={() => setFilter(f.key)}
          >
            <Text
              style={[
                styles.filterText,
                filter === f.key && styles.filterTextActive,
              ]}
            >
              {f.label}
              {f.key === "all" ? ` (${totalCount})` : ""}
            </Text>
          </Pressable>
        ))}
      </ScrollView>

      {/* Alert List */}
      <FlatList
        data={displayAlerts}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <AlertCard alert={item} onAcknowledge={acknowledge} />
        )}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        ItemSeparatorComponent={() => <View style={{ height: spacing.md }} />}
      />

      {/* Stats row */}
      <View style={styles.statsRow}>
        <View style={[styles.statCard, { backgroundColor: colors.bgSurface }]}>
          <Text style={styles.statValue}>99.8%</Text>
          <Text style={styles.statLabel}>UPTIME VIGIL</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: colors.bgAccentAlt }]}>
          <Text style={styles.statValue}>12ms</Text>
          <Text style={styles.statLabel}>THREAT LATENCY</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    height: 64,
  },
  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  logoIcon: {
    width: 16,
    height: 20,
    backgroundColor: colors.primary,
    borderRadius: 4,
    alignItems: "center",
    justifyContent: "center",
  },
  logoPupil: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.primaryLight,
  },
  headerTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["2xl"],
    color: colors.primary,
    letterSpacing: -1,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: radius.full,
    backgroundColor: colors.bgAccentSoft,
  },
  titleSection: {
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
  },
  subtitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.textMuted,
    letterSpacing: typography.tracking.widest,
  },
  title: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["5xl"],
    color: colors.textPrimary,
    letterSpacing: typography.tracking.tight,
  },
  filterScroll: {
    maxHeight: 48,
    marginTop: spacing.md,
  },
  filterRow: {
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
    alignItems: "center",
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.full,
    backgroundColor: colors.bgSurface,
  },
  filterChipActive: {
    backgroundColor: colors.primary,
  },
  filterText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  filterTextActive: {
    color: colors.primaryLight,
  },
  list: {
    padding: spacing.lg,
    paddingBottom: spacing["2xl"],
  },
  statsRow: {
    flexDirection: "row",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  statCard: {
    flex: 1,
    borderRadius: radius.lg,
    padding: spacing.md,
    height: 160,
    justifyContent: "flex-end",
  },
  statValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["4xl"],
    color: colors.textPrimary,
  },
  statLabel: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: 0.5,
  },
});
