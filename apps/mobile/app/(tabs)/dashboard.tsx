import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";
import { mockMetrics, mockChartData, mockPredictions, mockIntelFeed } from "../../lib/mock-data";
import { KPICard } from "../../components/KPICard";
import { MiniChart } from "../../components/MiniChart";
import { useSocket } from "../../hooks/useSocket";

export default function DashboardScreen() {
  const router = useRouter();
  useSocket();

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

      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* Hero: Threat Level Gauge */}
        <View style={styles.gaugeCard}>
          <Text style={styles.gaugeStatus}>STATUS: VIGILANT</Text>
          <View style={styles.gaugeCircle}>
            <View style={styles.gaugeRing}>
              <Text style={styles.gaugeValue}>74%</Text>
              <Text style={styles.gaugeLabel}>THREAT LEVEL</Text>
            </View>
          </View>
          <View style={styles.kpiRow}>
            <KPICard metric={mockMetrics[1]} />
            <KPICard metric={mockMetrics[2]} />
          </View>
        </View>

        {/* Global Ingress Chart */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Global Ingress</Text>
            <Text style={styles.sectionBadge}>LIVE STREAM</Text>
          </View>
          <MiniChart data={mockChartData} />
        </View>

        {/* Active Predictions */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Active Predictions</Text>
          <View style={styles.predGrid}>
            {mockPredictions.slice(0, 2).map((p) => (
              <View
                key={p.id}
                style={[
                  styles.predCard,
                  {
                    borderLeftColor:
                      p.severity === "critical"
                        ? colors.critical
                        : p.severity === "warning"
                        ? colors.warning
                        : colors.border,
                  },
                ]}
              >
                <Text style={styles.predTitle}>{p.title}</Text>
                <View style={styles.predSeverityRow}>
                  <View
                    style={[
                      styles.predDot,
                      {
                        backgroundColor:
                          p.severity === "critical"
                            ? colors.critical
                            : colors.warning,
                      },
                    ]}
                  />
                  <Text
                    style={[
                      styles.predSeverity,
                      {
                        color:
                          p.severity === "critical"
                            ? colors.critical
                            : colors.warning,
                      },
                    ]}
                  >
                    {p.severity === "critical" ? "Critical" : "Investigating"}
                  </Text>
                </View>
                <Text style={styles.predDesc}>
                  {p.confidence} Confidence{"\n"}
                  {p.description}
                </Text>
              </View>
            ))}
          </View>
          {/* Full-width card */}
          {mockPredictions[2] && (
            <Pressable style={styles.driftCard}>
              <View style={styles.driftIcon}>
                <Text style={styles.driftIconText}>{"~"}</Text>
              </View>
              <View style={styles.driftText}>
                <Text style={styles.driftTitle}>{mockPredictions[2].title}</Text>
                <Text style={styles.driftDesc}>{mockPredictions[2].description}</Text>
              </View>
              <Text style={styles.driftArrow}>{">"}</Text>
            </Pressable>
          )}
        </View>

        {/* Intelligence Feed */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Intelligence Feed</Text>
            <Pressable>
              <Text style={styles.viewAll}>VIEW ALL</Text>
            </Pressable>
          </View>
          {mockIntelFeed.slice(0, 2).map((item) => (
            <View
              key={item.id}
              style={[
                styles.feedItem,
                item.highlighted
                  ? { backgroundColor: colors.bg }
                  : { backgroundColor: colors.bgSurface },
              ]}
            >
              <View
                style={[
                  styles.feedBar,
                  {
                    backgroundColor: item.highlighted
                      ? colors.primary
                      : colors.textLight,
                  },
                ]}
              />
              <View style={styles.feedContent}>
                <Text style={styles.feedTime}>
                  {item.time} {"\u00B7"} {item.source}
                </Text>
                <Text style={styles.feedMessage}>{item.message}</Text>
              </View>
            </View>
          ))}
        </View>
      </ScrollView>

      {/* FAB */}
      <Pressable style={styles.fab}>
        <Text style={styles.fabIcon}>{"\u26A1"}</Text>
      </Pressable>
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
    width: 32,
    height: 32,
    borderRadius: radius.full,
    backgroundColor: colors.bgAccent,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingBottom: 120,
    gap: spacing.xl,
  },
  // Gauge
  gaugeCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.xl,
    padding: spacing.xl,
    alignItems: "center",
    ...shadows.cardUp,
  },
  gaugeStatus: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 1,
    alignSelf: "flex-end",
    marginBottom: spacing.md,
  },
  gaugeCircle: {
    width: 192,
    height: 192,
    borderRadius: 96,
    borderWidth: 12,
    borderColor: colors.bgSurface,
    alignItems: "center",
    justifyContent: "center",
  },
  gaugeRing: {
    alignItems: "center",
  },
  gaugeValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["6xl"],
    color: colors.primary,
    letterSpacing: -2.4,
  },
  gaugeLabel: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.sm,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 1.2,
  },
  kpiRow: {
    flexDirection: "row",
    gap: spacing.md,
    marginTop: spacing.xl,
    width: "100%",
  },
  // Section
  section: {
    gap: spacing.md,
  },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
  },
  sectionTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["2xl"],
    color: colors.textPrimary,
    letterSpacing: -0.5,
  },
  sectionBadge: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.primary,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  viewAll: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.primary,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  // Predictions
  predGrid: {
    flexDirection: "row",
    gap: spacing.md,
  },
  predCard: {
    flex: 1,
    backgroundColor: colors.bgCard,
    borderLeftWidth: 4,
    borderRadius: radius.xl,
    paddingLeft: spacing.lg,
    paddingRight: spacing.md,
    paddingVertical: spacing.md,
    justifyContent: "space-between",
    minHeight: 167,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  predTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  predSeverityRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginTop: spacing.sm,
  },
  predDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  predSeverity: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    textTransform: "uppercase",
  },
  predDesc: {
    fontFamily: typography.family.body,
    fontSize: 11,
    color: colors.textMuted,
    lineHeight: 13.75,
    marginTop: spacing.xs,
  },
  driftCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.bgCard,
    borderRadius: radius.xl,
    padding: 21,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
  },
  driftIcon: {
    width: 48,
    height: 48,
    borderRadius: radius.lg,
    backgroundColor: colors.bgAccent,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.md,
  },
  driftIconText: {
    fontSize: 20,
    color: colors.primary,
  },
  driftText: {
    flex: 1,
  },
  driftTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  driftDesc: {
    fontFamily: typography.family.body,
    fontSize: 11,
    color: colors.textMuted,
    lineHeight: 16.5,
  },
  driftArrow: {
    fontSize: 16,
    color: colors.textMuted,
  },
  // Feed
  feedItem: {
    flexDirection: "row",
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.md,
  },
  feedBar: {
    width: 3,
    height: 48,
    borderRadius: radius.full,
  },
  feedContent: {
    flex: 1,
    gap: spacing.xs,
  },
  feedTime: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  feedMessage: {
    fontFamily: typography.family.bodyMedium,
    fontSize: typography.size.md,
    color: colors.textPrimary,
    lineHeight: 20,
  },
  // FAB
  fab: {
    position: "absolute",
    bottom: 110,
    right: spacing.lg,
    width: 56,
    height: 56,
    borderRadius: radius.xl,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    ...shadows.fab,
  },
  fabIcon: {
    fontSize: 20,
    color: colors.primaryLight,
  },
});
