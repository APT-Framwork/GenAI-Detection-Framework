import { useMemo } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";
import { useColors } from "../../lib/theme-hook";
import {
  useDrift,
  useModels,
  type ModelHealth,
} from "../../lib/api/hooks";

type StatusKey = "operational" | "degraded" | "down" | "maintenance";

type StatusConfigEntry = {
  color: string;
  bg: string;
  label: string;
  icon: React.ComponentProps<typeof Ionicons>["name"];
};

function buildStatusConfig(
  c: ReturnType<typeof useColors>,
): Record<StatusKey, StatusConfigEntry> {
  return {
    operational: {
      color: c.success,
      bg: c.successBg,
      label: "Operational",
      icon: "checkmark-circle",
    },
    degraded: {
      color: c.warning,
      bg: c.warningBg,
      label: "Degraded",
      icon: "warning",
    },
    down: {
      color: c.critical,
      bg: c.criticalBg,
      label: "Down",
      icon: "close-circle",
    },
    maintenance: {
      color: c.warning,
      bg: c.warningBg,
      label: "Maintenance",
      icon: "construct",
    },
  };
}

function classifyStatus(model: ModelHealth): StatusKey {
  if (model.status === "degraded") return "degraded";
  if (model.status === "active") return "operational";
  return "degraded";
}

function fmtLatency(ms: number | null): string {
  if (ms === null) return "—";
  return ms < 10 ? `${ms.toFixed(1)}ms` : `${Math.round(ms)}ms`;
}

function fmtChecked(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  return `${Math.round(mins / 60)}h ago`;
}

export default function StatusScreen() {
  const c = useColors();
  const statusConfig = useMemo(() => buildStatusConfig(c), [c]);
  const modelsQ = useModels();
  const driftQ = useDrift(60);

  const models = modelsQ.data?.models ?? [];
  const driftByModel = useMemo(() => {
    const map = new Map<string, number>();
    for (const d of driftQ.data?.items ?? []) {
      map.set(d.model, d.klDivergence);
    }
    return map;
  }, [driftQ.data]);

  const operational = models.filter(
    (m) => classifyStatus(m) === "operational",
  ).length;
  const total = models.length;

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.bg }]}
      edges={["top"]}
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={[styles.headerTitle, { color: c.textPrimary }]}>
          Network
        </Text>
      </View>

      {/* Summary card */}
      <View style={[styles.summaryCard, { backgroundColor: c.bgCard }]}>
        <View style={styles.summaryLeft}>
          {modelsQ.isLoading ? (
            <ActivityIndicator color={c.primary} />
          ) : (
            <>
              <Text style={[styles.summaryValue, { color: c.textPrimary }]}>
                {operational}/{total}
              </Text>
              <Text style={[styles.summaryLabel, { color: c.textMuted }]}>
                MODELS OPERATIONAL
              </Text>
            </>
          )}
        </View>
        <View
          style={[
            styles.summaryIndicator,
            {
              backgroundColor:
                total > 0 && operational === total
                  ? c.successBg
                  : c.warningBg,
            },
          ]}
        >
          <Ionicons
            name={
              total > 0 && operational === total
                ? "shield-checkmark"
                : "shield-half"
            }
            size={28}
            color={
              total > 0 && operational === total
                ? c.success
                : c.warning
            }
          />
        </View>
      </View>

      {/* Service list */}
      {modelsQ.isError ? (
        <View style={[styles.errorCard, { backgroundColor: c.bgCard }]}>
          <Text style={[styles.errorTitle, { color: c.textPrimary }]}>
            Couldn't reach /monitoring/models
          </Text>
          <Text style={[styles.errorDesc, { color: c.textMuted }]}>
            {(modelsQ.error as Error)?.message ?? "Check backend connection."}
          </Text>
          <Pressable
            style={[styles.retryBtn, { backgroundColor: c.primary }]}
            onPress={() => void modelsQ.refetch()}
          >
            <Text style={[styles.retryText, { color: c.white }]}>RETRY</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={models}
          keyExtractor={(item) => item.name}
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
          ListEmptyComponent={
            modelsQ.isLoading ? null : (
              <View style={styles.emptyCard}>
                <Text style={[styles.errorTitle, { color: c.textPrimary }]}>
                  No models reporting
                </Text>
                <Text style={[styles.errorDesc, { color: c.textMuted }]}>
                  Inference workers haven't posted a health check yet.
                </Text>
              </View>
            )
          }
          refreshControl={
            <RefreshControl
              refreshing={modelsQ.isRefetching}
              onRefresh={() => {
                void modelsQ.refetch();
                void driftQ.refetch();
              }}
              tintColor={c.primary}
            />
          }
          renderItem={({ item }) => {
            const key = classifyStatus(item);
            const cfg = statusConfig[key];
            const drift = item.driftKl ?? driftByModel.get(item.name) ?? null;
            return (
              <View
                style={[styles.serviceCard, { backgroundColor: c.bgCard }]}
              >
                <View style={styles.serviceHeader}>
                  <View
                    style={[
                      styles.statusIndicator,
                      { backgroundColor: cfg.bg },
                    ]}
                  >
                    <Ionicons name={cfg.icon} size={16} color={cfg.color} />
                  </View>
                  <View style={styles.serviceInfo}>
                    <Text style={[styles.serviceName, { color: c.textPrimary }]}>
                      {item.name} · v{item.version}
                    </Text>
                    <Text style={[styles.serviceStatus, { color: cfg.color }]}>
                      {cfg.label}
                    </Text>
                  </View>
                </View>
                <View
                  style={[
                    styles.serviceMetrics,
                    { backgroundColor: c.bgSurface },
                  ]}
                >
                  <View style={styles.metric}>
                    <Text style={[styles.metricValue, { color: c.textPrimary }]}>
                      {fmtLatency(item.p50LatencyMs)}
                    </Text>
                    <Text style={[styles.metricLabel, { color: c.textMuted }]}>
                      P50
                    </Text>
                  </View>
                  <View style={[styles.metricDivider, { backgroundColor: c.border }]} />
                  <View style={styles.metric}>
                    <Text style={[styles.metricValue, { color: c.textPrimary }]}>
                      {fmtLatency(item.p99LatencyMs)}
                    </Text>
                    <Text style={[styles.metricLabel, { color: c.textMuted }]}>
                      P99
                    </Text>
                  </View>
                  <View style={[styles.metricDivider, { backgroundColor: c.border }]} />
                  <View style={styles.metric}>
                    <Text
                      style={[
                        styles.metricValue,
                        { color: drift !== null && drift > 0.2 ? c.critical : c.textPrimary },
                      ]}
                    >
                      {drift === null ? "—" : drift.toFixed(3)}
                    </Text>
                    <Text style={[styles.metricLabel, { color: c.textMuted }]}>
                      DRIFT KL
                    </Text>
                  </View>
                  <View style={[styles.metricDivider, { backgroundColor: c.border }]} />
                  <View style={styles.metric}>
                    <Text style={[styles.metricValue, { color: c.textPrimary }]}>
                      {fmtChecked(item.lastHealthCheck)}
                    </Text>
                    <Text style={[styles.metricLabel, { color: c.textMuted }]}>
                      CHECKED
                    </Text>
                  </View>
                </View>
              </View>
            );
          }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
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
  summaryLeft: { gap: spacing.xs },
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
  list: { padding: spacing.lg, paddingBottom: spacing["3xl"] },
  errorCard: {
    margin: spacing.lg,
    padding: spacing.lg,
    gap: spacing.sm,
    alignItems: "center",
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    ...shadows.card,
  },
  emptyCard: {
    padding: spacing.lg,
    gap: spacing.sm,
    alignItems: "center",
  },
  errorTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.lg,
    color: colors.textPrimary,
  },
  errorDesc: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
    textAlign: "center",
  },
  retryBtn: {
    marginTop: spacing.sm,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
  },
  retryText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.white,
    letterSpacing: 1,
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
  serviceInfo: { flex: 1, gap: 2 },
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
  metric: { flex: 1, alignItems: "center", gap: 2 },
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
