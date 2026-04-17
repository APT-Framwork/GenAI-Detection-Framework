import { View, Text, StyleSheet, FlatList } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";
import { mockSystemStatus, type Service } from "../../lib/mock-data";

const STATUS_CONFIG: Record<
  Service["status"],
  { color: string; bg: string; label: string; icon: React.ComponentProps<typeof Ionicons>["name"] }
> = {
  operational: { color: colors.success, bg: colors.successBg, label: "Operational", icon: "checkmark-circle" },
  degraded: { color: "#c77900", bg: "rgba(199,121,0,0.08)", label: "Degraded", icon: "warning" },
  down: { color: colors.critical, bg: colors.criticalBg, label: "Down", icon: "close-circle" },
  maintenance: { color: colors.warning, bg: colors.warningBg, label: "Maintenance", icon: "construct" },
};

export default function StatusScreen() {
  const operational = mockSystemStatus.filter((s) => s.status === "operational").length;
  const total = mockSystemStatus.length;

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Network</Text>
      </View>

      {/* Summary card */}
      <View style={styles.summaryCard}>
        <View style={styles.summaryLeft}>
          <Text style={styles.summaryValue}>
            {operational}/{total}
          </Text>
          <Text style={styles.summaryLabel}>SERVICES OPERATIONAL</Text>
        </View>
        <View
          style={[
            styles.summaryIndicator,
            {
              backgroundColor:
                operational === total ? colors.successBg : colors.warningBg,
            },
          ]}
        >
          <Ionicons
            name={operational === total ? "shield-checkmark" : "shield-half"}
            size={28}
            color={operational === total ? colors.success : colors.warning}
          />
        </View>
      </View>

      {/* Service list */}
      <FlatList
        data={mockSystemStatus}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
        renderItem={({ item }) => {
          const cfg = STATUS_CONFIG[item.status];
          return (
            <View style={styles.serviceCard}>
              <View style={styles.serviceHeader}>
                <View style={[styles.statusIndicator, { backgroundColor: cfg.bg }]}>
                  <Ionicons name={cfg.icon} size={16} color={cfg.color} />
                </View>
                <View style={styles.serviceInfo}>
                  <Text style={styles.serviceName}>{item.name}</Text>
                  <Text style={[styles.serviceStatus, { color: cfg.color }]}>
                    {cfg.label}
                  </Text>
                </View>
              </View>
              <View style={styles.serviceMetrics}>
                <View style={styles.metric}>
                  <Text style={styles.metricValue}>{item.uptime}</Text>
                  <Text style={styles.metricLabel}>UPTIME</Text>
                </View>
                <View style={styles.metricDivider} />
                <View style={styles.metric}>
                  <Text style={styles.metricValue}>{item.latency}</Text>
                  <Text style={styles.metricLabel}>LATENCY</Text>
                </View>
                <View style={styles.metricDivider} />
                <View style={styles.metric}>
                  <Text style={styles.metricValue}>{item.lastCheck}</Text>
                  <Text style={styles.metricLabel}>CHECKED</Text>
                </View>
              </View>
            </View>
          );
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
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
  summaryCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginHorizontal: spacing.lg,
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    ...shadows.card,
  },
  summaryLeft: {
    gap: spacing.xs,
  },
  summaryValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["4xl"],
    color: colors.textPrimary,
    letterSpacing: -1,
  },
  summaryLabel: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: 1,
  },
  summaryIndicator: {
    width: 56,
    height: 56,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  list: {
    padding: spacing.lg,
    paddingBottom: spacing["3xl"],
  },
  serviceCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.md,
    ...shadows.card,
  },
  serviceHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  statusIndicator: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  serviceInfo: {
    flex: 1,
    gap: 2,
  },
  serviceName: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  serviceStatus: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  serviceMetrics: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.bgSurface,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  metric: {
    flex: 1,
    alignItems: "center",
    gap: 2,
  },
  metricValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.textPrimary,
  },
  metricLabel: {
    fontFamily: typography.family.heading,
    fontSize: 8,
    color: colors.textMuted,
    letterSpacing: 0.5,
  },
  metricDivider: {
    width: 1,
    height: 24,
    backgroundColor: colors.border,
  },
});
