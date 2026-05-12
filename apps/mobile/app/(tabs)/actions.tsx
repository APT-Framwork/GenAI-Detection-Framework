/**
 * Actions / Approvals — the SOC analyst's one-tap response surface.
 *
 * Lists DQN actions decided by the platform with their approval status.
 * Pending actions can be approved or declined inline (with a quick reason
 * for declines). Backed by /api/v1/actions.
 */

import { useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, shadows, spacing, typography } from "../../lib/theme";
import {
  useActions,
  useApproveAction,
  useDeclineAction,
  type DqnAction,
} from "../../lib/api/hooks";

type StatusFilter = "pending" | "approved" | "declined" | "all";

function actionLabel(a: string): string {
  const map: Record<string, string> = {
    BLOCK_USER_IP: "Block User IP",
    ISOLATE_HOST: "Isolate Host",
    BLOCK_DOMAIN: "Block Domain",
    KILL_PROCESS: "Kill Process",
    QUARANTINE_FILE: "Quarantine File",
    ESCALATE: "Escalate",
    LOW_ALERT: "Low Alert",
    MONITOR: "Monitor",
  };
  return map[a] ?? a.replace(/_/g, " ").toLowerCase();
}

function actionTone(a: string): { fg: string; bg: string } {
  if (a.startsWith("BLOCK") || a === "ISOLATE_HOST" || a === "KILL_PROCESS") {
    return { fg: colors.critical, bg: colors.criticalBg };
  }
  if (a === "QUARANTINE_FILE" || a === "ESCALATE") {
    return { fg: colors.warning, bg: colors.warningBg };
  }
  return { fg: colors.primary, bg: colors.primaryLight };
}

function timeAgo(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export default function ActionsScreen() {
  const router = useRouter();
  const [filter, setFilter] = useState<StatusFilter>("pending");
  const [declining, setDeclining] = useState<DqnAction | null>(null);
  const [declineReason, setDeclineReason] = useState("");

  const q = useActions(filter);
  const approveMut = useApproveAction();
  const declineMut = useDeclineAction();

  const items = q.data?.items ?? [];
  const counts = q.data?.counts ?? { pending: 0, approved: 0, declined: 0 };

  const filterTabs: { key: StatusFilter; label: string; count?: number }[] = useMemo(
    () => [
      { key: "pending", label: "Pending", count: counts.pending },
      { key: "approved", label: "Approved", count: counts.approved },
      { key: "declined", label: "Declined", count: counts.declined },
      { key: "all", label: "All" },
    ],
    [counts],
  );

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <Text style={styles.eyebrow}>RESPONSE</Text>
        <Text style={styles.title}>Approvals</Text>
        <Text style={styles.subtitle}>
          {counts.pending > 0
            ? `${counts.pending} action${counts.pending === 1 ? "" : "s"} waiting on you`
            : "No pending actions"}
        </Text>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filterRow}
      >
        {filterTabs.map((t) => {
          const active = t.key === filter;
          return (
            <Pressable
              key={t.key}
              style={[styles.filterChip, active && styles.filterChipActive]}
              onPress={() => setFilter(t.key)}
            >
              <Text
                style={[
                  styles.filterChipText,
                  active && styles.filterChipTextActive,
                ]}
              >
                {t.label.toUpperCase()}
                {t.count != null ? `  ${t.count}` : ""}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <FlatList
        data={items}
        keyExtractor={(a) => a.actionId}
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
                name="checkmark-circle-outline"
                size={40}
                color={colors.textLight}
              />
              <Text style={styles.emptyTitle}>All clear</Text>
              <Text style={styles.emptyBody}>
                Nothing in this bucket. The RL agent is autonomous on low-risk
                actions and only escalates here for review.
              </Text>
            </View>
          )
        }
        renderItem={({ item }) => {
          const tone = actionTone(item.action);
          const pending = item.status === "pending";
          return (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <View style={[styles.tag, { backgroundColor: tone.bg }]}>
                  <Text style={[styles.tagText, { color: tone.fg }]}>
                    {actionLabel(item.action)}
                  </Text>
                </View>
                <Text style={styles.time}>{timeAgo(item.decidedAt)}</Text>
              </View>

              {item.rationale ? (
                <Text style={styles.rationale} numberOfLines={3}>
                  {item.rationale}
                </Text>
              ) : null}

              <View style={styles.meta}>
                {item.chainId && (
                  <Pressable
                    onPress={() =>
                      router.push(`/analysis/${item.chainId}` as never)
                    }
                    style={styles.metaPill}
                  >
                    <Ionicons
                      name="git-network-outline"
                      size={12}
                      color={colors.textMuted}
                    />
                    <Text style={styles.metaText}>
                      Chain {item.chainId.slice(0, 8)}
                    </Text>
                  </Pressable>
                )}
                {item.hostId && (
                  <View style={styles.metaPill}>
                    <Ionicons
                      name="hardware-chip-outline"
                      size={12}
                      color={colors.textMuted}
                    />
                    <Text style={styles.metaText}>
                      Host {item.hostId.slice(0, 8)}
                    </Text>
                  </View>
                )}
              </View>

              {pending ? (
                <View style={styles.actionRow}>
                  <Pressable
                    style={[styles.btn, styles.declineBtn]}
                    disabled={declineMut.isPending || approveMut.isPending}
                    onPress={() => {
                      setDeclining(item);
                      setDeclineReason("");
                    }}
                  >
                    <Ionicons name="close" size={16} color={colors.critical} />
                    <Text style={[styles.btnText, { color: colors.critical }]}>
                      DECLINE
                    </Text>
                  </Pressable>
                  <Pressable
                    style={[styles.btn, styles.approveBtn]}
                    disabled={approveMut.isPending}
                    onPress={() => approveMut.mutate(item.actionId)}
                  >
                    {approveMut.isPending &&
                    approveMut.variables === item.actionId ? (
                      <ActivityIndicator size="small" color={colors.white} />
                    ) : (
                      <>
                        <Ionicons name="checkmark" size={16} color={colors.white} />
                        <Text style={[styles.btnText, { color: colors.white }]}>
                          APPROVE
                        </Text>
                      </>
                    )}
                  </Pressable>
                </View>
              ) : (
                <View
                  style={[
                    styles.stateBadge,
                    item.status === "approved"
                      ? { backgroundColor: colors.successBg }
                      : { backgroundColor: colors.criticalBg },
                  ]}
                >
                  <Text
                    style={[
                      styles.stateText,
                      item.status === "approved"
                        ? { color: colors.success }
                        : { color: colors.critical },
                    ]}
                  >
                    {item.status.toUpperCase()}
                    {item.approvedBy ? `  by ${item.approvedBy}` : ""}
                  </Text>
                  {item.declineReason ? (
                    <Text style={styles.declineReason}>
                      Reason: {item.declineReason}
                    </Text>
                  ) : null}
                </View>
              )}
            </View>
          );
        }}
      />

      {/* Decline reason modal */}
      <Modal
        animationType="fade"
        transparent
        visible={!!declining}
        onRequestClose={() => setDeclining(null)}
      >
        <View style={styles.modalScrim}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Decline action</Text>
            <Text style={styles.modalSub}>
              {declining ? actionLabel(declining.action) : ""}
            </Text>
            <TextInput
              style={styles.modalInput}
              placeholder="Reason (e.g. false positive, business critical, …)"
              placeholderTextColor={colors.textLight}
              value={declineReason}
              onChangeText={setDeclineReason}
              multiline
            />
            <View style={styles.modalActions}>
              <Pressable
                style={[styles.btn, styles.declineBtn, { flex: 1 }]}
                onPress={() => setDeclining(null)}
              >
                <Text style={[styles.btnText, { color: colors.textMuted }]}>
                  CANCEL
                </Text>
              </Pressable>
              <Pressable
                style={[styles.btn, styles.approveBtn, { flex: 1 }]}
                disabled={declineReason.trim().length === 0 || declineMut.isPending}
                onPress={() => {
                  if (!declining) return;
                  declineMut.mutate(
                    { actionId: declining.actionId, reason: declineReason.trim() },
                    { onSettled: () => setDeclining(null) },
                  );
                }}
              >
                {declineMut.isPending ? (
                  <ActivityIndicator size="small" color={colors.white} />
                ) : (
                  <Text style={[styles.btnText, { color: colors.white }]}>
                    DECLINE
                  </Text>
                )}
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
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
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  tag: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.full,
  },
  tagText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    letterSpacing: typography.tracking.wide,
  },
  time: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  rationale: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textBody,
    lineHeight: 20,
  },
  meta: { flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" },
  metaPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    backgroundColor: colors.bgSurface,
    borderRadius: radius.full,
  },
  metaText: {
    fontFamily: typography.family.mono,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  actionRow: {
    flexDirection: "row",
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
  btn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
  },
  btnText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    letterSpacing: typography.tracking.wide,
  },
  declineBtn: {
    borderWidth: 1,
    borderColor: colors.critical,
    backgroundColor: colors.criticalBg,
  },
  approveBtn: { backgroundColor: colors.primary },
  stateBadge: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    gap: 4,
  },
  stateText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    letterSpacing: typography.tracking.wider,
  },
  declineReason: {
    fontFamily: typography.family.body,
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
  modalScrim: {
    flex: 1,
    backgroundColor: "rgba(11,14,20,0.45)",
    justifyContent: "center",
    paddingHorizontal: spacing.lg,
  },
  modalCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.md,
    ...shadows.card,
  },
  modalTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["2xl"],
    color: colors.textPrimary,
  },
  modalSub: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  modalInput: {
    minHeight: 90,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.bgSurface,
    borderRadius: radius.md,
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textPrimary,
    textAlignVertical: "top",
  },
  modalActions: { flexDirection: "row", gap: spacing.sm },
});
