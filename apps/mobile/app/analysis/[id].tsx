import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";

import {
  useChainDwellTime,
  useChainInfection,
  useCkcProgression,
} from "../../lib/api/hooks";
import { useChainLogStream } from "../../lib/api/sse";
import { colors, radius, shadows, spacing, typography } from "../../lib/theme";

function fmtDuration(secs: number): string {
  if (secs < 60) return `${Math.round(secs)}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  const hrs = Math.floor(secs / 3600);
  const mins = Math.round((secs % 3600) / 60);
  return `${hrs}h ${mins}m`;
}

export default function ChainAnalysisScreen() {
  const { id: idParam } = useLocalSearchParams<{ id: string }>();
  const id = Array.isArray(idParam) ? idParam[0] : idParam;
  const chainId = id ?? null;
  const router = useRouter();

  const dwell = useChainDwellTime(chainId);
  const infection = useChainInfection(chainId);
  const ckc = useCkcProgression(chainId);
  const logs = useChainLogStream(chainId);

  const status = dwell.data?.status ?? "—";
  const isOpen = status === "open";

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      {/* Header */}
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="chevron-back" size={24} color={colors.primary} />
        </Pressable>
        <Text style={styles.headerTitle}>Chain Analysis</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* Summary */}
        <View style={styles.summaryCard}>
          <Text style={styles.chainIdLabel}>CHAIN ID</Text>
          <Text style={styles.chainId} numberOfLines={1}>
            {chainId ?? "—"}
          </Text>
          <View style={styles.statusRow}>
            <View
              style={[
                styles.statusBadge,
                {
                  backgroundColor: isOpen
                    ? colors.criticalBg
                    : colors.successBg,
                },
              ]}
            >
              <Text
                style={[
                  styles.statusText,
                  { color: isOpen ? colors.critical : colors.success },
                ]}
              >
                {status.toUpperCase()}
              </Text>
            </View>
            {dwell.data?.closeReason ? (
              <Text style={styles.closeReason}>{dwell.data.closeReason}</Text>
            ) : null}
          </View>
        </View>

        {/* KPIs */}
        <View style={styles.kpiGrid}>
          <View style={styles.kpiCard}>
            <Text style={styles.kpiValue}>
              {dwell.isLoading
                ? "…"
                : dwell.data
                ? fmtDuration(dwell.data.durationSeconds)
                : "—"}
            </Text>
            <Text style={styles.kpiLabel}>DWELL TIME</Text>
          </View>
          <View style={styles.kpiCard}>
            <Text style={styles.kpiValue}>
              {infection.isLoading
                ? "…"
                : infection.data
                ? `${infection.data.infectedCount}/${infection.data.totalCount}`
                : "—"}
            </Text>
            <Text style={styles.kpiLabel}>INFECTED HOSTS</Text>
          </View>
          <View style={styles.kpiCard}>
            <Text style={styles.kpiValue}>
              {infection.isLoading
                ? "…"
                : infection.data
                ? `${Math.round(infection.data.percent)}%`
                : "—"}
            </Text>
            <Text style={styles.kpiLabel}>RADIUS</Text>
          </View>
        </View>

        {/* CKC progression */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Kill Chain Progression</Text>
          {ckc.isLoading ? (
            <ActivityIndicator color={colors.primary} />
          ) : (ckc.data?.stages ?? []).length === 0 ? (
            <Text style={styles.emptyHint}>No stages recorded yet.</Text>
          ) : (
            <View style={styles.timelineCard}>
              {ckc.data!.stages.map((s, idx, arr) => (
                <View key={`${s.ckcStage}-${s.enteredAt}`} style={styles.timelineRow}>
                  <View style={styles.timelineLeft}>
                    <View style={styles.timelineDot} />
                    {idx < arr.length - 1 ? (
                      <View style={styles.timelineLine} />
                    ) : null}
                  </View>
                  <View style={styles.timelineContent}>
                    <Text style={styles.timelineStage}>
                      S{s.ckcStage} · {s.ckcStageName.replace(/_/g, " ")}
                    </Text>
                    <Text style={styles.timelineMeta}>
                      {s.dqnAction ?? "—"} · {s.enteredAt.slice(11, 19)}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>

        {/* Live forensic logs */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Forensic Logs</Text>
            <View style={styles.sseBadgeRow}>
              <View
                style={[
                  styles.sseDot,
                  {
                    backgroundColor:
                      logs.status === "open"
                        ? colors.success
                        : logs.status === "connecting"
                        ? colors.warning
                        : colors.textLight,
                  },
                ]}
              />
              <Text style={styles.sseBadgeText}>
                {logs.status === "open"
                  ? "LIVE"
                  : logs.status === "connecting"
                  ? "CONNECTING"
                  : "OFFLINE"}
              </Text>
            </View>
          </View>
          {logs.events.length === 0 ? (
            <Text style={styles.emptyHint}>
              Waiting for the next log line…
            </Text>
          ) : (
            logs.events.slice(0, 15).map((e) => (
              <View key={`${e.alertId}-${e.ts}`} style={styles.logRow}>
                <Text style={styles.logTs}>{e.ts.slice(11, 19)}</Text>
                <Text style={styles.logAgent}>
                  {e.agentName ?? "unknown"}
                </Text>
                <Text style={styles.logBody} numberOfLines={2}>
                  {e.ruleDescription ?? e.rawLog ?? "—"}
                </Text>
              </View>
            ))
          )}
        </View>
      </ScrollView>
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
    height: 56,
  },
  headerTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.lg,
    color: colors.textPrimary,
    letterSpacing: typography.tracking.tight,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing["3xl"],
    gap: spacing.lg,
  },
  summaryCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
    ...shadows.card,
  },
  chainIdLabel: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: 1,
  },
  chainId: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.lg,
    color: colors.textPrimary,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: radius.full,
  },
  statusText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    letterSpacing: 1,
  },
  closeReason: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  kpiGrid: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  kpiCard: {
    flex: 1,
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.md,
    alignItems: "center",
    gap: 2,
    ...shadows.card,
  },
  kpiValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["2xl"],
    color: colors.textPrimary,
  },
  kpiLabel: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    color: colors.textMuted,
    letterSpacing: 0.8,
  },
  section: { gap: spacing.md },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  sectionTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.textPrimary,
    letterSpacing: -0.5,
  },
  sseBadgeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
  },
  sseDot: { width: 8, height: 8, borderRadius: 4 },
  sseBadgeText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: 1,
  },
  emptyHint: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  timelineCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.md,
    ...shadows.card,
  },
  timelineRow: {
    flexDirection: "row",
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  timelineLeft: {
    alignItems: "center",
    paddingTop: 4,
  },
  timelineDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.primary,
  },
  timelineLine: {
    flex: 1,
    width: 2,
    backgroundColor: colors.border,
    marginTop: 4,
  },
  timelineContent: { flex: 1, gap: 2 },
  timelineStage: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  timelineMeta: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  logRow: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.sm,
    gap: 2,
    marginBottom: spacing.xs,
    ...shadows.card,
  },
  logTs: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.primary,
    letterSpacing: 0.8,
  },
  logAgent: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  logBody: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textBody,
    lineHeight: 18,
  },
});
