/**
 * Vigilance Feed — real-time SSE stream of every detection coming out of
 * the platform. This is the SOC analyst's "what's happening right now"
 * surface; tap any row to jump to the chain investigation.
 *
 * Backed by /api/v1/streams/live-feed via `useLiveFeed()`. The hook keeps
 * up to 200 events in memory and re-emits each new alert as the SSE
 * connection delivers it.
 */

import { useMemo, useState } from "react";
import {
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, shadows, spacing, typography } from "../../lib/theme";
import { useColors } from "../../lib/theme-hook";
import { useLiveFeed, type LiveFeedEvent } from "../../lib/api/sse";

type SeverityBucket = "all" | "critical" | "high" | "medium" | "low";

const STAGE_NAMES = [
  "Benign",
  "Recon",
  "Weaponization",
  "Delivery",
  "Exploitation",
  "Installation",
  "C2",
  "Actions",
];

function bucketOf(ev: LiveFeedEvent): Exclude<SeverityBucket, "all"> {
  // Mirror the backend's severity-from-VAE buckets so the filter is
  // intuitive to anyone who's used /alerts.
  const p = ev.vaeMaliciousProb ?? 0;
  if (p >= 0.9 || (ev.ckcStage ?? 0) >= 6) return "critical";
  if (p >= 0.7 || (ev.ckcStage ?? 0) >= 4) return "high";
  if (p >= 0.4) return "medium";
  return "low";
}

function bucketColor(
  b: Exclude<SeverityBucket, "all">,
  c: ReturnType<typeof useColors>,
) {
  switch (b) {
    case "critical": return c.critical;
    case "high":     return c.critical;
    case "medium":   return c.warning;
    case "low":      return c.info;
  }
}

function timeAgo(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.round(hrs / 24)}d`;
}

export default function VigilanceFeedScreen() {
  const router = useRouter();
  const c = useColors();
  const [filter, setFilter] = useState<SeverityBucket>("all");
  const [refreshing, setRefreshing] = useState(false);
  const { events, status } = useLiveFeed();

  const filtered = useMemo(() => {
    if (filter === "all") return events;
    return events.filter((ev) => bucketOf(ev) === filter);
  }, [events, filter]);

  const counts = useMemo(() => {
    const c = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const ev of events) c[bucketOf(ev)]++;
    return c;
  }, [events]);

  const statusLabel = {
    idle: "STANDBY",
    connecting: "CONNECTING",
    open: "LIVE",
    closed: "CLOSED",
    error: "RECONNECTING",
  }[status];
  const statusColor =
    status === "open" ? c.success
    : status === "error" ? c.critical
    : c.textMuted;

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.bg }]}
      edges={["top"]}
    >
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={[styles.eyebrow, { color: c.textMuted }]}>VIGILANCE</Text>
          <Text style={[styles.title, { color: c.textPrimary }]}>Live Feed</Text>
        </View>
        <View
          style={[
            styles.statusPill,
            { borderColor: statusColor, backgroundColor: c.bgCard },
          ]}
        >
          <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
          <Text style={[styles.statusText, { color: statusColor }]}>{statusLabel}</Text>
        </View>
      </View>

      {/* Counters */}
      <View style={styles.kpiRow}>
        <View style={[styles.kpiCard, { backgroundColor: c.bgCard }]}>
          <Text style={[styles.kpiValue, { color: c.textPrimary }]}>
            {events.length}
          </Text>
          <Text style={[styles.kpiLabel, { color: c.textMuted }]}>BUFFERED</Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: c.bgCard }]}>
          <Text style={[styles.kpiValue, { color: c.critical }]}>
            {counts.critical + counts.high}
          </Text>
          <Text style={[styles.kpiLabel, { color: c.textMuted }]}>
            CRIT + HIGH
          </Text>
        </View>
        <View style={[styles.kpiCard, { backgroundColor: c.bgCard }]}>
          <Text style={[styles.kpiValue, { color: c.warning }]}>
            {counts.medium}
          </Text>
          <Text style={[styles.kpiLabel, { color: c.textMuted }]}>MEDIUM</Text>
        </View>
      </View>

      {/* Filters */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filterRow}
      >
        {(["all", "critical", "high", "medium", "low"] as SeverityBucket[]).map(
          (b) => {
            const active = b === filter;
            return (
              <Pressable
                key={b}
                style={[
                  styles.filterChip,
                  { backgroundColor: c.bgCard, borderColor: c.border },
                  active && { backgroundColor: c.primary, borderColor: c.primary },
                ]}
                onPress={() => setFilter(b)}
              >
                <Text
                  style={[
                    styles.filterChipText,
                    { color: c.textMuted },
                    active && { color: c.white },
                  ]}
                >
                  {b.toUpperCase()}
                </Text>
              </Pressable>
            );
          },
        )}
      </ScrollView>

      {/* Feed list */}
      <FlatList
        data={filtered}
        keyExtractor={(ev) => ev.alertId}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              setTimeout(() => setRefreshing(false), 500);
            }}
            tintColor={c.primary}
          />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons
              name={status === "open" ? "ear-outline" : "cloud-offline-outline"}
              size={40}
              color={c.textLight}
            />
            <Text style={[styles.emptyTitle, { color: c.textPrimary }]}>
              {status === "open"
                ? "Listening for events"
                : "Waiting for stream"}
            </Text>
            <Text style={[styles.emptyBody, { color: c.textMuted }]}>
              {status === "open"
                ? "New detections will appear here as the platform emits them."
                : "Reconnecting to the live feed…"}
            </Text>
          </View>
        }
        renderItem={({ item }) => {
          const sev = bucketOf(item);
          const accent = bucketColor(sev, c);
          const stage =
            item.ckcStageName ||
            STAGE_NAMES[item.ckcStage ?? 0] ||
            `Stage ${item.ckcStage ?? 0}`;
          return (
            <Pressable
              style={[
                styles.eventCard,
                { backgroundColor: c.bgCard, borderLeftColor: accent },
              ]}
              onPress={() => {
                if (item.chainId) {
                  router.push(`/analysis/${item.chainId}` as never);
                }
              }}
            >
              <View style={styles.eventTop}>
                <Text style={[styles.eventSev, { color: accent }]}>
                  {sev.toUpperCase()}
                </Text>
                <Text style={[styles.eventTime, { color: c.textMuted }]}>
                  {timeAgo(item.occurredAt)}
                </Text>
              </View>
              <Text style={[styles.eventStage, { color: c.textPrimary }]}>
                CKC · {stage}
                {item.dqnActionName ? `  ·  RL: ${item.dqnActionName}` : ""}
              </Text>
              <View style={styles.eventMetrics}>
                {item.vaeMaliciousProb != null && (
                  <View style={styles.metric}>
                    <Text style={[styles.metricLabel, { color: c.textMuted }]}>
                      VAE
                    </Text>
                    <Text style={[styles.metricValue, { color: c.primary }]}>
                      {(item.vaeMaliciousProb * 100).toFixed(0)}%
                    </Text>
                  </View>
                )}
                {item.gnnNodeRisk != null && (
                  <View style={styles.metric}>
                    <Text style={[styles.metricLabel, { color: c.textMuted }]}>
                      GNN
                    </Text>
                    <Text style={[styles.metricValue, { color: c.primary }]}>
                      {(item.gnnNodeRisk * 100).toFixed(0)}%
                    </Text>
                  </View>
                )}
                {item.aeAnomalyScore != null && (
                  <View style={styles.metric}>
                    <Text style={[styles.metricLabel, { color: c.textMuted }]}>
                      AE
                    </Text>
                    <Text style={[styles.metricValue, { color: c.primary }]}>
                      {item.aeAnomalyScore.toFixed(2)}
                    </Text>
                  </View>
                )}
              </View>
              {(item.mitreTechniques?.length ?? 0) > 0 && (
                <View style={styles.mitreRow}>
                  {(item.mitreTechniques ?? []).slice(0, 4).map((t) => (
                    <View
                      key={t}
                      style={[
                        styles.mitreChip,
                        { backgroundColor: c.primaryLight },
                      ]}
                    >
                      <Text style={[styles.mitreChipText, { color: c.primary }]}>
                        {t}
                      </Text>
                    </View>
                  ))}
                </View>
              )}
              {item.chainId && (
                <View
                  style={[styles.eventFooter, { borderTopColor: c.border }]}
                >
                  <Ionicons
                    name="git-network-outline"
                    size={12}
                    color={c.textMuted}
                  />
                  <Text style={[styles.eventChain, { color: c.textMuted }]}>
                    Chain {item.chainId.slice(0, 8)}
                  </Text>
                  <Ionicons
                    name="chevron-forward"
                    size={14}
                    color={c.textMuted}
                    style={{ marginLeft: "auto" }}
                  />
                </View>
              )}
            </Pressable>
          );
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-end",
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
  },
  headerLeft: { gap: 2 },
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
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderWidth: 1,
    borderRadius: radius.full,
    backgroundColor: colors.bgCard,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusText: {
    fontFamily: typography.family.heading,
    fontSize: 10,
    letterSpacing: typography.tracking.wider,
  },
  kpiRow: {
    flexDirection: "row",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  kpiCard: {
    flex: 1,
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
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
    letterSpacing: typography.tracking.wider,
  },
  filterRow: {
    paddingHorizontal: spacing.md,
    gap: 6,
    marginBottom: spacing.sm,
  },
  filterChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.full,
    backgroundColor: colors.bgCard,
    borderWidth: 1,
    borderColor: colors.border,
  },
  filterChipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  filterChipText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: typography.tracking.wider,
  },
  filterChipTextActive: { color: colors.white },
  list: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing["2xl"],
    gap: spacing.sm,
  },
  eventCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    borderLeftWidth: 4,
    padding: spacing.md,
    gap: spacing.xs,
    ...shadows.card,
  },
  eventTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  eventSev: {
    fontFamily: typography.family.heading,
    fontSize: 10,
    letterSpacing: typography.tracking.wider,
  },
  eventTime: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  eventStage: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  eventMetrics: {
    flexDirection: "row",
    gap: spacing.md,
    marginTop: 2,
  },
  metric: { flexDirection: "row", gap: 4, alignItems: "baseline" },
  metricLabel: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    color: colors.textMuted,
    letterSpacing: typography.tracking.wide,
  },
  metricValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.primary,
  },
  mitreRow: { flexDirection: "row", gap: 4, flexWrap: "wrap", marginTop: 4 },
  mitreChip: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    backgroundColor: colors.primaryLight,
    borderRadius: radius.full,
  },
  mitreChipText: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    color: colors.primary,
    letterSpacing: 0.4,
  },
  eventFooter: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginTop: 4,
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  eventChain: {
    fontFamily: typography.family.mono,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  empty: {
    alignItems: "center",
    paddingVertical: spacing["3xl"],
    gap: spacing.sm,
  },
  emptyTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.lg,
    color: colors.textPrimary,
  },
  emptyBody: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
    textAlign: "center",
    paddingHorizontal: spacing["2xl"],
  },
});
