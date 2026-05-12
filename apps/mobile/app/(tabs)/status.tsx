import { useMemo, useState } from "react";
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
import {
  MODEL_REGISTRY,
  compositeMetrics,
  findLiveRow,
  type ModelMetrics,
  type ModelTint,
} from "../../lib/model-registry";

type StatusKey = "operational" | "degraded" | "down" | "maintenance";

type StatusConfigEntry = {
  color: string;
  bg: string;
  label: string;
  icon: React.ComponentProps<typeof Ionicons>["name"];
};

const TINT_HEX: Record<ModelTint, string> = {
  cyan: "#00f2ff",
  purple: "#a78bfa",
  amber: "#fbbf24",
  emerald: "#34d399",
  blue: "#60a5fa",
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

function classifyStatus(live: ModelHealth | undefined): StatusKey {
  if (!live) return "maintenance";
  if (live.status === "degraded") return "degraded";
  if (live.status === "active") return "operational";
  return "degraded";
}

function fmtLatency(ms: number | null): string {
  if (ms === null) return "—";
  return ms < 10 ? `${ms.toFixed(1)}ms` : `${Math.round(ms)}ms`;
}

function fmtChecked(iso: string | undefined): string {
  if (!iso) return "—";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  return `${Math.round(mins / 60)}h ago`;
}

function pct(v: number | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function fixed(v: number | undefined): string {
  return v == null ? "—" : v.toFixed(3);
}

type Row = ModelMetrics & {
  live: ModelHealth | undefined;
  statusKey: StatusKey;
};

export default function StatusScreen() {
  const c = useColors();
  const statusConfig = useMemo(() => buildStatusConfig(c), [c]);
  const modelsQ = useModels();
  const driftQ = useDrift(60);
  const [expanded, setExpanded] = useState<string | null>(null);

  const driftByModel = useMemo(() => {
    const map = new Map<string, number>();
    for (const d of driftQ.data?.items ?? []) {
      map.set(d.model.toLowerCase(), d.klDivergence);
    }
    return map;
  }, [driftQ.data]);

  const liveRows = modelsQ.data?.models ?? [];

  const rows: Row[] = useMemo(
    () =>
      MODEL_REGISTRY.map((entry) => {
        const live = findLiveRow(entry, liveRows);
        return { ...entry, live, statusKey: classifyStatus(live) };
      }),
    [liveRows],
  );

  const composite = useMemo(() => compositeMetrics(), []);

  const operational = rows.filter((r) => r.statusKey === "operational").length;
  const total = rows.length;

  const avgDriftKl = useMemo(() => {
    const xs = liveRows
      .map((m) => m.driftKl)
      .filter((v): v is number => typeof v === "number");
    if (xs.length === 0) return null;
    return xs.reduce((a, b) => a + b, 0) / xs.length;
  }, [liveRows]);

  const driftFor = (row: Row): number | null =>
    row.live?.driftKl ??
    driftByModel.get(row.live?.name?.toLowerCase() ?? "") ??
    driftByModel.get(row.name.toLowerCase().split(" ")[0]) ??
    null;

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.bg }]}
      edges={["top"]}
    >
      <View style={styles.header}>
        <Text style={[styles.eyebrow, { color: c.textMuted }]}>AI ENGINE</Text>
        <Text style={[styles.headerTitle, { color: c.textPrimary }]}>
          Model Health
        </Text>
        <Text style={[styles.headerSub, { color: c.textMuted }]}>
          Test-set metrics from training notebooks · live signals refresh every 30s.
        </Text>
      </View>

      {/* KPI strip — composite test-set + live aggregates */}
      <View style={styles.kpiRow}>
        <View style={[styles.kpiCard, { backgroundColor: c.bgCard }]}>
          <Text style={[styles.kpiValue, { color: c.textPrimary }]}>
            {composite.accuracyPct.toFixed(1)}%
          </Text>
          <Text style={[styles.kpiLabel, { color: c.textMuted }]}>
            COMPOSITE ACC
          </Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: c.bgCard }]}>
          <Text style={[styles.kpiValue, { color: c.textPrimary }]}>
            {composite.f1.toFixed(3)}
          </Text>
          <Text style={[styles.kpiLabel, { color: c.textMuted }]}>
            COMPOSITE F1
          </Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: c.bgCard }]}>
          <Text
            style={[
              styles.kpiValue,
              {
                color:
                  avgDriftKl == null
                    ? c.textMuted
                    : avgDriftKl > 0.2
                    ? c.critical
                    : c.success,
              },
            ]}
          >
            {avgDriftKl == null ? "—" : avgDriftKl.toFixed(4)}
          </Text>
          <Text style={[styles.kpiLabel, { color: c.textMuted }]}>
            AVG DRIFT KL
          </Text>
        </View>
      </View>

      {/* Summary */}
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
                total > 0 && operational === total ? c.successBg : c.warningBg,
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
            color={total > 0 && operational === total ? c.success : c.warning}
          />
        </View>
      </View>

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
          data={rows}
          keyExtractor={(item) => item.name}
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
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
            const cfg = statusConfig[item.statusKey];
            const tint = TINT_HEX[item.color];
            const drift = driftFor(item);
            const isOpen = expanded === item.name;
            return (
              <View style={[styles.serviceCard, { backgroundColor: c.bgCard }]}>
                <View style={styles.serviceHeader}>
                  <View
                    style={[
                      styles.statusIndicator,
                      { backgroundColor: tint + "22" },
                    ]}
                  >
                    <Ionicons name="hardware-chip-outline" size={16} color={tint} />
                  </View>
                  <View style={styles.serviceInfo}>
                    <Text style={[styles.serviceName, { color: c.textPrimary }]}>
                      {item.name}
                    </Text>
                    <Text style={[styles.serviceArch, { color: c.textMuted }]}>
                      {item.architecture}
                    </Text>
                  </View>
                  <View
                    style={[
                      styles.statusPill,
                      { backgroundColor: cfg.bg, borderColor: cfg.color },
                    ]}
                  >
                    <Ionicons name={cfg.icon} size={11} color={cfg.color} />
                    <Text style={[styles.statusPillText, { color: cfg.color }]}>
                      {cfg.label}
                    </Text>
                  </View>
                </View>

                <View
                  style={[
                    styles.metricsRow,
                    { backgroundColor: c.bgSurface },
                  ]}
                >
                  <Metric label="ACC" value={pct(item.metrics.accuracy)} c={c} />
                  <Divider c={c} />
                  <Metric label="F1" value={fixed(item.metrics.f1)} c={c} />
                  <Divider c={c} />
                  <Metric label="AUC" value={fixed(item.metrics.auc)} c={c} />
                  <Divider c={c} />
                  <Metric
                    label="DRIFT"
                    value={drift === null ? "—" : drift.toFixed(3)}
                    c={c}
                    accent={
                      drift !== null && drift > 0.2 ? c.critical : undefined
                    }
                  />
                </View>

                <Pressable
                  onPress={() => setExpanded(isOpen ? null : item.name)}
                  style={styles.detailToggle}
                >
                  <Text style={[styles.detailToggleText, { color: tint }]}>
                    {isOpen ? "Hide details" : "View details"}
                  </Text>
                  <Ionicons
                    name={isOpen ? "chevron-up" : "chevron-down"}
                    size={14}
                    color={tint}
                  />
                </Pressable>

                {isOpen && (
                  <View style={[styles.detailBlock, { borderTopColor: c.border }]}>
                    <Text style={[styles.description, { color: c.textBody }]}>
                      {item.description}
                    </Text>
                    <View style={styles.detailGrid}>
                      <Detail label="Precision" value={pct(item.metrics.precision)} c={c} />
                      <Detail label="Recall" value={pct(item.metrics.recall)} c={c} />
                      {item.metrics.threshold != null && (
                        <Detail
                          label="Threshold"
                          value={item.metrics.threshold.toFixed(4)}
                          c={c}
                        />
                      )}
                      {(item.metrics.extras ?? []).map((e) => (
                        <Detail key={e.label} label={e.label} value={e.value} c={c} />
                      ))}
                    </View>

                    <View style={[styles.liveBlock, { borderTopColor: c.border }]}>
                      <Detail
                        label="P50 latency"
                        value={fmtLatency(item.live?.p50LatencyMs ?? null)}
                        c={c}
                      />
                      <Detail
                        label="P99 latency"
                        value={fmtLatency(item.live?.p99LatencyMs ?? null)}
                        c={c}
                      />
                      <Detail
                        label="Last check"
                        value={fmtChecked(item.live?.lastHealthCheck)}
                        c={c}
                      />
                      <Detail
                        label="Weights"
                        value={
                          item.live?.weightsSha256
                            ? item.live.weightsSha256.slice(0, 10) + "…"
                            : "—"
                        }
                        c={c}
                        mono
                      />
                    </View>

                    <Text style={[styles.sourceLine, { color: c.textMuted }]}>
                      Source · {item.source}
                    </Text>
                  </View>
                )}
              </View>
            );
          }}
        />
      )}
    </SafeAreaView>
  );
}

function Metric({
  label,
  value,
  c,
  accent,
}: {
  label: string;
  value: string;
  c: ReturnType<typeof useColors>;
  accent?: string;
}) {
  return (
    <View style={styles.metric}>
      <Text style={[styles.metricValue, { color: accent ?? c.textPrimary }]}>
        {value}
      </Text>
      <Text style={[styles.metricLabel, { color: c.textMuted }]}>{label}</Text>
    </View>
  );
}

function Divider({ c }: { c: ReturnType<typeof useColors> }) {
  return <View style={[styles.metricDivider, { backgroundColor: c.border }]} />;
}

function Detail({
  label,
  value,
  c,
  mono,
}: {
  label: string;
  value: string;
  c: ReturnType<typeof useColors>;
  mono?: boolean;
}) {
  return (
    <View style={styles.detailCell}>
      <Text style={[styles.detailLabel, { color: c.textMuted }]}>{label}</Text>
      <Text
        style={[
          styles.detailValue,
          { color: c.textPrimary },
          mono && { fontFamily: typography.family.mono },
        ]}
        numberOfLines={1}
      >
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    gap: 4,
  },
  eyebrow: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    letterSpacing: typography.tracking.widest,
  },
  headerTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["3xl"],
    letterSpacing: typography.tracking.tight,
  },
  headerSub: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xs,
    lineHeight: 16,
  },
  kpiRow: {
    flexDirection: "row",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  kpiCard: {
    flex: 1,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    ...shadows.card,
  },
  kpiValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
  },
  kpiLabel: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    letterSpacing: typography.tracking.wider,
    marginTop: 2,
  },
  summaryCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginHorizontal: spacing.lg,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    ...shadows.card,
  },
  summaryLeft: { gap: spacing.xs },
  summaryValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["4xl"],
    letterSpacing: -1,
  },
  summaryLabel: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
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
    borderRadius: radius.lg,
    ...shadows.card,
  },
  errorTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.lg,
  },
  errorDesc: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    textAlign: "center",
  },
  retryBtn: {
    marginTop: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
  },
  retryText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    letterSpacing: 1,
  },
  serviceCard: {
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
  },
  serviceArch: {
    fontFamily: typography.family.heading,
    fontSize: 10,
    letterSpacing: 0.5,
    textTransform: "uppercase",
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.full,
    borderWidth: 1,
  },
  statusPillText: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    letterSpacing: 0.6,
    textTransform: "uppercase",
  },
  metricsRow: {
    flexDirection: "row",
    alignItems: "center",
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  metric: { flex: 1, alignItems: "center", gap: 2 },
  metricValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
  },
  metricLabel: {
    fontFamily: typography.family.heading,
    fontSize: 8,
    letterSpacing: 0.5,
  },
  metricDivider: { width: 1, height: 24 },
  detailToggle: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
  },
  detailToggleText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    letterSpacing: 0.6,
    textTransform: "uppercase",
  },
  detailBlock: {
    borderTopWidth: 1,
    paddingTop: spacing.md,
    gap: spacing.md,
  },
  description: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    lineHeight: 18,
  },
  detailGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
  },
  detailCell: { minWidth: "30%", gap: 2 },
  detailLabel: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    letterSpacing: 0.5,
    textTransform: "uppercase",
  },
  detailValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
  },
  liveBlock: {
    borderTopWidth: 1,
    paddingTop: spacing.sm,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
  },
  sourceLine: {
    fontFamily: typography.family.mono,
    fontSize: 10,
  },
});
