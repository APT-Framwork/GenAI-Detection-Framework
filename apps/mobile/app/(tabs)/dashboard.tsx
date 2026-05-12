import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";
import { useColors } from "../../lib/theme-hook";
import { KPICard } from "../../components/KPICard";
import { MiniChart } from "../../components/MiniChart";
import { SkeletonBlock } from "../../components/Skeleton";
import { KillChainStrip } from "../../components/KillChainStrip";
import { MitreStrip } from "../../components/MitreStrip";
import { CavixLogo } from "../../components/CavixLogo";
import {
  useAttackVector,
  useGlobalRisk,
  useMitreCoverage,
  useRefreshSentinelInsight,
  useSentinelInsight,
} from "../../lib/api/hooks";
import { useLiveFeed, type LiveFeedEvent } from "../../lib/api/sse";
import { useUserStore } from "../../stores/user-store";

export default function DashboardScreen() {
  const router = useRouter();
  const user = useUserStore((s) => s.user);
  const qc = useQueryClient();
  const c = useColors();

  const attackVector = useAttackVector("1h");
  const globalRisk = useGlobalRisk("1h");
  const insight = useSentinelInsight();
  const refreshInsight = useRefreshSentinelInsight();
  const mitre = useMitreCoverage("24h");

  // Live feed SSE. Each event invalidates dashboard aggregates + the
  // unack-count badge so the UI converges without waiting for the
  // polling tick.
  const onLiveEvent = useCallback(
    (_: LiveFeedEvent) => {
      qc.invalidateQueries({ queryKey: ["alerts", "unack-count"] });
      qc.invalidateQueries({ queryKey: ["dashboard", "attack-vector"] });
      qc.invalidateQueries({ queryKey: ["dashboard", "global-risk"] });
    },
    [qc],
  );
  const liveFeed = useLiveFeed({ enabled: true, onEvent: onLiveEvent });

  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        attackVector.refetch(),
        globalRisk.refetch(),
        insight.refetch(),
      ]);
    } finally {
      setRefreshing(false);
    }
  }, [attackVector, globalRisk, insight]);

  // Threat level gauge — percentage from global risk (0..1 → 0..100).
  const threatPct = Math.round((globalRisk.data?.globalRisk ?? 0) * 100);

  // KPI cards: total alerts in window + anomaly rate.
  const kpiAlerts = useMemo(
    () => ({
      id: "alerts-1h",
      label: "ALERTS / 1H",
      value: String(attackVector.data?.totalAlerts ?? 0),
    }),
    [attackVector.data?.totalAlerts],
  );
  const kpiAnomaly = useMemo(
    () => ({
      id: "anomaly-rate",
      label: "ANOMALY RATE",
      value: `${Math.round(
        (globalRisk.data?.components.anomalyRate ?? 0) * 100,
      )}`,
      unit: "%",
    }),
    [globalRisk.data?.components.anomalyRate],
  );

  // Trend chart — map GlobalRiskTrendPoint[] into the chart's ChartPoint[].
  const chartData = useMemo(() => {
    const trend = globalRisk.data?.trend ?? [];
    if (trend.length === 0) return [];
    return trend.map((p, i) => ({
      day: i,
      value: p.value,
      label: p.ts,
    }));
  }, [globalRisk.data?.trend]);

  // Active predictions — derived from attack-vector stage buckets.
  // Pick the top 2 non-BENIGN stages with a count > 0.
  const predictions = useMemo(() => {
    const stages = (attackVector.data?.stages ?? []).filter(
      (s) => s.ckcStage !== 0 && s.count > 0,
    );
    const top = stages
      .slice()
      .sort((a, b) => b.count - a.count)
      .slice(0, 2);
    return top.map((s) => {
      const severity: "critical" | "warning" =
        s.ckcStage >= 5 ? "critical" : "warning";
      return {
        id: `pred-${s.ckcStage}`,
        title: s.ckcName.replace(/_/g, " "),
        severity,
        confidence: `${s.count} ALERTS`,
        description:
          severity === "critical"
            ? "High-severity stage active in the current window."
            : "Chain activity in this stage — investigating.",
      };
    });
  }, [attackVector.data?.stages]);

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.bg }]}
      edges={["top"]}
    >
      {/* Header */}
      <View style={styles.header}>
        <CavixLogo width={96} color={c.primary} />
        <Pressable
          onPress={() => router.push("/(tabs)/profile" as never)}
          hitSlop={10}
          style={[styles.avatar, { backgroundColor: c.bgAccent }]}
        >
          <Text style={[styles.avatarText, { color: c.primary }]}>
            {user?.email.slice(0, 2).toUpperCase() ?? "—"}
          </Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={c.primary}
          />
        }
      >
        {/* Hero: Threat Level Gauge */}
        <View style={[styles.gaugeCard, { backgroundColor: c.bgCard }]}>
          <Text style={[styles.gaugeStatus, { color: c.textMuted }]}>
            STATUS:{" "}
            {threatPct >= 70
              ? "CRITICAL"
              : threatPct >= 40
              ? "ELEVATED"
              : "VIGILANT"}
          </Text>
          <View style={[styles.gaugeCircle, { borderColor: c.bgSurface }]}>
            <View style={styles.gaugeRing}>
              {globalRisk.isLoading ? (
                <ActivityIndicator color={c.primary} size="large" />
              ) : (
                <>
                  <Text style={[styles.gaugeValue, { color: c.primary }]}>
                    {threatPct}%
                  </Text>
                  <Text style={[styles.gaugeLabel, { color: c.textMuted }]}>
                    THREAT LEVEL
                  </Text>
                </>
              )}
            </View>
          </View>
          <View style={styles.kpiRow}>
            <KPICard metric={kpiAlerts} />
            <KPICard metric={kpiAnomaly} />
          </View>
        </View>

        {/* Global Ingress Chart */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={[styles.sectionTitle, { color: c.textPrimary }]}>
              Global Ingress
            </Text>
            <Text style={[styles.sectionBadge, { color: c.textMuted }]}>
              {globalRisk.isFetching ? "UPDATING…" : "LIVE STREAM"}
            </Text>
          </View>
          {chartData.length > 0 ? (
            <MiniChart data={chartData} />
          ) : (
            <View style={styles.chartEmpty}>
              <Text style={[styles.emptyHint, { color: c.textMuted }]}>
                {globalRisk.isLoading
                  ? "Loading trend…"
                  : "No data in the last hour."}
              </Text>
            </View>
          )}
        </View>

        {/* Cyber Kill Chain — per-stage event counts in the last hour */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={[styles.sectionTitle, { color: c.textPrimary }]}>
              Kill Chain · 1h
            </Text>
            <Text style={[styles.sectionBadge, { color: c.textMuted }]}>
              {attackVector.data?.totalAlerts ?? 0} EVENTS
            </Text>
          </View>
          <KillChainStrip stages={attackVector.data?.stages ?? []} />
        </View>

        {/* MITRE ATT&CK tactics — most active in the last 24h */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={[styles.sectionTitle, { color: c.textPrimary }]}>
              MITRE Tactics · 24h
            </Text>
            <Text style={[styles.sectionBadge, { color: c.textMuted }]}>
              {mitre.isFetching ? "UPDATING…" : `${mitre.data?.tactics.length ?? 0} TACTICS`}
            </Text>
          </View>
          <MitreStrip tactics={mitre.data?.tactics ?? []} />
        </View>

        {/* Active Predictions */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: c.textPrimary }]}>
            Active Predictions
          </Text>
          {predictions.length > 0 ? (
            <View style={styles.predGrid}>
              {predictions.map((p) => (
                <View
                  key={p.id}
                  style={[
                    styles.predCard,
                    {
                      borderLeftColor:
                        p.severity === "critical"
                          ? colors.critical
                          : colors.warning,
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
                      {p.severity === "critical"
                        ? "Critical"
                        : "Investigating"}
                    </Text>
                  </View>
                  <Text style={styles.predDesc}>
                    {p.confidence}
                    {"\n"}
                    {p.description}
                  </Text>
                </View>
              ))}
            </View>
          ) : (
            <Text style={[styles.emptyHint, { color: c.textMuted }]}>
              No active kill-chain stages in the current window.
            </Text>
          )}
        </View>

        {/* Sentinel Insight */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={[styles.sectionTitle, { color: c.textPrimary }]}>
              Sentinel Insight
            </Text>
            <Pressable
              onPress={() => refreshInsight.mutate()}
              disabled={refreshInsight.isPending || insight.isFetching}
              hitSlop={10}
            >
              <Text style={[styles.viewAll, { color: c.primary }]}>
                {refreshInsight.isPending || insight.isFetching
                  ? "REFRESHING…"
                  : "REFRESH"}
              </Text>
            </Pressable>
          </View>
          <View style={[styles.insightCard, { backgroundColor: c.bgCard }]}>
            {insight.isLoading ? (
              <SkeletonBlock lines={3} lineHeight={12} />
            ) : (
              <>
                <Text style={[styles.insightBody, { color: c.textBody }]}>
                  {insight.data?.insight ??
                    "Insight unavailable — check backend connection."}
                </Text>
                {insight.data?.modelVersion ? (
                  <Text style={[styles.insightMeta, { color: c.textMuted }]}>
                    {insight.data.stale ? "STALE · " : ""}
                    {insight.data.modelVersion}
                  </Text>
                ) : null}
              </>
            )}
          </View>
        </View>

        {/* Live feed pulse — quick preview, deeper view on the Feed tab */}
        <Pressable
          style={[styles.feedCta, { backgroundColor: c.bgCard }]}
          onPress={() => router.push("/(tabs)/feed" as never)}
        >
          <View style={styles.feedCtaLeft}>
            <View
              style={[
                styles.sseDot,
                {
                  backgroundColor:
                    liveFeed.status === "open"
                      ? c.success
                      : liveFeed.status === "connecting"
                        ? c.warning
                        : c.textLight,
                },
              ]}
            />
            <View style={{ flex: 1 }}>
              <Text style={[styles.feedCtaTitle, { color: c.textPrimary }]}>
                {liveFeed.status === "open"
                  ? "Live feed connected"
                  : liveFeed.status === "connecting"
                    ? "Connecting to feed…"
                    : "Feed offline"}
              </Text>
              <Text style={[styles.feedCtaSub, { color: c.textMuted }]}>
                {liveFeed.events.length} event
                {liveFeed.events.length === 1 ? "" : "s"} buffered — tap to open
              </Text>
            </View>
          </View>
          <Text style={[styles.feedCtaArrow, { color: c.primary }]}>{"→"}</Text>
        </Pressable>
              </ScrollView>

      {/* FAB — navigate to alerts */}
      <Pressable
        style={styles.fab}
        onPress={() => router.push("/(tabs)/feed" as never)}
      >
        <Text style={styles.fabIcon}>{"\u26A1"}</Text>
      </Pressable>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    height: 64,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: radius.full,
    backgroundColor: colors.bgAccent,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.primary,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingBottom: 120,
    gap: spacing.xl,
  },
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
  gaugeRing: { alignItems: "center" },
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
  section: { gap: spacing.md },
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
  chartEmpty: {
    height: 192,
    borderRadius: radius.lg,
    backgroundColor: colors.bgCard,
    alignItems: "center",
    justifyContent: "center",
    ...shadows.card,
  },
  emptyHint: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  predGrid: { flexDirection: "row", gap: spacing.md },
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
  predDot: { width: 8, height: 8, borderRadius: 4 },
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
  insightCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.xl,
    padding: spacing.lg,
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
  },
  insightBody: {
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textBody,
    lineHeight: 20,
  },
  insightMeta: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  sseDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  feedCta: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    ...shadows.card,
  },
  feedCtaLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    flex: 1,
  },
  feedCtaTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  feedCtaSub: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    marginTop: 2,
  },
  feedCtaArrow: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.primary,
  },
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
  fabIcon: { fontSize: 20, color: colors.primaryLight },
});
