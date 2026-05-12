/**
 * Cases / Triage queue — open attack chains grouped by triage status.
 *
 * The SOC analyst's "what needs my attention" view: every chain the
 * platform has correlated, with its current triage state. Tapping a row
 * drills into /analysis/[chainId]; the status pill cycles through
 * new → investigating → contained → closed.
 */

import { useMemo, useState } from "react";
import {
  ActivityIndicator,
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
import {
  useCases,
  useSetTriageStatus,
  type CaseItem,
  type TriageStatus,
} from "../../lib/api/hooks";

const STAGE_NAMES = [
  "Benign",
  "Recon",
  "Weapon",
  "Delivery",
  "Exploit",
  "Install",
  "C2",
  "Actions",
];

const STATUS_FLOW: Record<string, TriageStatus> = {
  new: "investigating",
  investigating: "contained",
  contained: "closed",
  closed: "new",
};

function statusTone(s: string): { fg: string; bg: string } {
  switch (s) {
    case "new":           return { fg: colors.critical, bg: colors.criticalBg };
    case "investigating": return { fg: colors.warning,  bg: colors.warningBg };
    case "contained":     return { fg: colors.primary,  bg: colors.primaryLight };
    case "closed":        return { fg: colors.textMuted, bg: colors.bgSurface };
    default:              return { fg: colors.textMuted, bg: colors.bgSurface };
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

export default function CasesScreen() {
  const router = useRouter();
  const c = useColors();
  const [filter, setFilter] = useState<TriageStatus | "all">("all");
  const q = useCases({ status: filter });
  const setStatusMut = useSetTriageStatus();

  const counts: Record<string, number> = (q.data?.counts ?? {}) as Record<
    string,
    number
  >;
  const items = q.data?.items ?? [];

  const tabs: { key: TriageStatus | "all"; label: string }[] = useMemo(
    () => [
      { key: "all",           label: "All" },
      { key: "new",           label: "New" },
      { key: "investigating", label: "Investigating" },
      { key: "contained",     label: "Contained" },
      { key: "closed",        label: "Closed" },
    ],
    [],
  );

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.bg }]}
      edges={["top"]}
    >
      <View style={styles.header}>
        <Text style={[styles.eyebrow, { color: c.textMuted }]}>TRIAGE</Text>
        <Text style={[styles.title, { color: c.textPrimary }]}>Cases</Text>
        <Text style={[styles.subtitle, { color: c.textMuted }]}>
          {Object.values(counts).reduce<number>((a, b) => a + b, 0)} chains tracked
        </Text>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filterRow}
      >
        {tabs.map((t) => {
          const active = t.key === filter;
          const count = t.key === "all"
            ? Object.values(counts).reduce<number>((a, b) => a + b, 0)
            : (counts[t.key] ?? 0);
          return (
            <Pressable
              key={t.key}
              style={[
                styles.filterChip,
                { backgroundColor: c.bgCard, borderColor: c.border },
                active && { backgroundColor: c.primary, borderColor: c.primary },
              ]}
              onPress={() => setFilter(t.key)}
            >
              <Text
                style={[
                  styles.filterChipText,
                  { color: c.textMuted },
                  active && { color: c.white },
                ]}
              >
                {t.label.toUpperCase()}  {count}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <FlatList
        data={items}
        keyExtractor={(c) => c.chainId}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={q.isFetching} onRefresh={() => q.refetch()} />
        }
        ListEmptyComponent={
          q.isLoading ? (
            <View style={styles.empty}>
              <ActivityIndicator color={colors.primary} />
            </View>
          ) : (
            <View style={styles.empty}>
              <Ionicons
                name="briefcase-outline"
                size={40}
                color={colors.textLight}
              />
              <Text style={styles.emptyTitle}>No cases</Text>
              <Text style={styles.emptyBody}>
                The triage queue is empty for this filter.
              </Text>
            </View>
          )
        }
        renderItem={({ item }) => (
          <CaseRow
            item={item}
            onOpen={() => router.push(`/analysis/${item.chainId}` as never)}
            onCycle={() =>
              setStatusMut.mutate({
                chainId: item.chainId,
                status:
                  STATUS_FLOW[item.status ?? "new"] ?? "investigating",
              })
            }
            updating={
              setStatusMut.isPending &&
              setStatusMut.variables?.chainId === item.chainId
            }
          />
        )}
      />
    </SafeAreaView>
  );
}

function CaseRow({
  item,
  onOpen,
  onCycle,
  updating,
}: {
  item: CaseItem;
  onOpen: () => void;
  onCycle: () => void;
  updating: boolean;
}) {
  const c = useColors();
  // Backend `status` is the triage state (new/investigating/contained/closed).
  // Some legacy chains may arrive with it nulled out — fall back to "new" so
  // the row still renders.
  const triage = item.status ?? "new";
  const tone = statusTone(triage);
  const stage =
    item.maxCkcStageName
      ?? STAGE_NAMES[item.maxCkcStage ?? 0]
      ?? "Stage";
  const probPct = item.maxVaeProb != null
    ? `${Math.round(item.maxVaeProb * 100)}%`
    : null;
  const ownerName = item.assignee?.name ?? null;
  const chainIdShort = item.chainId ? item.chainId.slice(0, 8) : "—";
  return (
    <Pressable
      style={[styles.card, { backgroundColor: c.bgCard }]}
      onPress={onOpen}
    >
      <View style={styles.cardTop}>
        <Pressable
          onPress={onCycle}
          disabled={updating}
          style={[styles.statusPill, { backgroundColor: tone.bg }]}
        >
          {updating ? (
            <ActivityIndicator size="small" color={tone.fg} />
          ) : (
            <Text style={[styles.statusPillText, { color: tone.fg }]}>
              {triage.toUpperCase()}
            </Text>
          )}
        </Pressable>
        <Text style={[styles.time, { color: c.textMuted }]}>
          {item.lastSeenAt ? `${timeAgo(item.lastSeenAt)} ago` : ""}
        </Text>
      </View>

      <Text style={[styles.host, { color: c.textPrimary }]}>
        {item.hostName
          ?? (item.hostIp ? item.hostIp : null)
          ?? (item.hostId ? `Host ${item.hostId.slice(0, 8)}` : "Unknown host")}
      </Text>

      <View style={styles.metricRow}>
        <View style={styles.metricCell}>
          <Text style={styles.metricLabel}>CKC</Text>
          <Text style={styles.metricValue}>{stage}</Text>
        </View>
        {probPct && (
          <View style={styles.metricCell}>
            <Text style={styles.metricLabel}>VAE</Text>
            <Text style={styles.metricValue}>{probPct}</Text>
          </View>
        )}
        <View style={styles.metricCell}>
          <Text style={styles.metricLabel}>EVENTS</Text>
          <Text style={styles.metricValue}>{item.stepCount ?? 0}</Text>
        </View>
        {ownerName && (
          <View style={[styles.metricCell, { flex: 1.5 }]}>
            <Text style={styles.metricLabel}>OWNER</Text>
            <Text style={styles.metricValue} numberOfLines={1}>
              {ownerName}
            </Text>
          </View>
        )}
      </View>

      <View style={styles.cardFooter}>
        <Text style={styles.chainId}>Chain {chainIdShort}</Text>
        <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    gap: 2,
  },
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
  subtitle: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  filterRow: { paddingHorizontal: spacing.md, gap: 6, marginBottom: spacing.sm },
  filterChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.full,
    backgroundColor: colors.bgCard,
    borderWidth: 1,
    borderColor: colors.border,
  },
  filterChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
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
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadows.card,
  },
  cardTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  statusPill: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.full,
  },
  statusPillText: {
    fontFamily: typography.family.heading,
    fontSize: 10,
    letterSpacing: typography.tracking.wider,
  },
  time: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  host: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.lg,
    color: colors.textPrimary,
  },
  metricRow: { flexDirection: "row", gap: spacing.md },
  metricCell: { gap: 2 },
  metricLabel: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    color: colors.textMuted,
    letterSpacing: typography.tracking.wide,
  },
  metricValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.primary,
  },
  cardFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  chainId: {
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
