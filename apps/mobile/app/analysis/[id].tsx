import { useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";

import {
  useAddChainNote,
  useChainActivity,
  useChainDwellTime,
  useChainInfection,
  useChainNotes,
  useChainPredictions,
  useCkcProgression,
  usePlaybooks,
} from "../../lib/api/hooks";
import { useChainLogStream } from "../../lib/api/sse";
import { colors, radius, shadows, spacing, typography } from "../../lib/theme";
import { KillChainStrip } from "../../components/KillChainStrip";

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
  const predictions = useChainPredictions(chainId);
  const notes = useChainNotes(chainId);
  const activity = useChainActivity(chainId);
  const addNote = useAddChainNote();

  // Latest CKC stage + technique drive the playbook lookup. The stage
  // comes from the progression; the first technique we see in the live
  // log stream is the best proxy for "what's the current TTP".
  const currentStage = predictions.data?.currentStage ?? null;
  const playbooks = usePlaybooks({
    stage: currentStage,
    technique: null,
  });

  const [noteDraft, setNoteDraft] = useState("");

  const status = dwell.data?.status ?? "—";
  const isOpen = status === "open";

  // Per-stage event counts for the KillChainStrip — derive from CKC
  // progression. Each stage appears once per chain (the latest entry), so
  // count is mostly 0 or 1; the visualization is more about *trajectory*.
  const stageCounts = useMemo(() => {
    const map = new Map<number, number>();
    for (const s of ckc.data?.stages ?? []) {
      map.set(s.ckcStage, (map.get(s.ckcStage) ?? 0) + 1);
    }
    return Array.from(map.entries()).map(([ckcStage, count]) => ({
      ckcStage,
      ckcName: `S${ckcStage}`,
      count,
    }));
  }, [ckc.data?.stages]);

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

        {/* Compact CKC visual */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Kill Chain Position</Text>
          <KillChainStrip
            stages={stageCounts}
            highlightStage={currentStage ?? undefined}
          />
        </View>

        {/* AI next-stage predictions */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Next-Stage Predictions</Text>
          {predictions.isLoading ? (
            <ActivityIndicator color={colors.primary} />
          ) : (predictions.data?.probabilities ?? []).length === 0 ? (
            <Text style={styles.emptyHint}>
              No active predictions for this chain.
            </Text>
          ) : (
            <View style={styles.predictionsCard}>
              {predictions.data!.probabilities.slice(0, 3).map((p) => {
                const pct = Math.round((p.prob ?? 0) * 100);
                const hot = pct >= 60;
                return (
                  <View key={p.ckcStage} style={styles.predictionRow}>
                    <View style={styles.predictionMain}>
                      <Text style={styles.predictionStage}>
                        S{p.ckcStage} · {(p.ckcStageName ?? "").replace(/_/g, " ")}
                      </Text>
                      <View style={styles.predictionBar}>
                        <View
                          style={[
                            styles.predictionFill,
                            {
                              width: `${pct}%`,
                              backgroundColor: hot
                                ? colors.critical
                                : colors.primary,
                            },
                          ]}
                        />
                      </View>
                    </View>
                    <Text
                      style={[
                        styles.predictionPct,
                        { color: hot ? colors.critical : colors.primary },
                      ]}
                    >
                      {pct}%
                    </Text>
                  </View>
                );
              })}
            </View>
          )}
        </View>

        {/* Recommended response playbooks — prefer matched, fall back to fallback */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Recommended Response</Text>
          {playbooks.isLoading ? (
            <ActivityIndicator color={colors.primary} />
          ) : (() => {
              const matched = playbooks.data?.matched ?? [];
              const fallback = playbooks.data?.fallback ?? null;
              const pb = matched[0] ?? fallback;
              const isFallback = !matched[0] && !!fallback;
              if (!pb) {
                return (
                  <Text style={styles.emptyHint}>
                    No matching playbook for this stage yet.
                  </Text>
                );
              }
              return (
                <View style={styles.playbookCard}>
                  <View style={styles.playbookHeader}>
                    <Text style={styles.playbookName}>{pb.title}</Text>
                    {isFallback && (
                      <View style={styles.fallbackBadge}>
                        <Text style={styles.fallbackText}>FALLBACK</Text>
                      </View>
                    )}
                  </View>
                  {pb.description ? (
                    <Text style={styles.playbookDesc} numberOfLines={3}>
                      {pb.description}
                    </Text>
                  ) : null}
                  {(pb.steps ?? []).slice(0, 4).map((s, i) => (
                    <View key={s.stepId} style={styles.stepRow}>
                      <Text style={styles.stepIdx}>{i + 1}</Text>
                      <Text style={styles.stepText} numberOfLines={2}>
                        {s.title}
                      </Text>
                    </View>
                  ))}
                </View>
              );
            })()}
        </View>

        {/* Investigation notes */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Investigation Notes</Text>
          <View style={styles.noteInputRow}>
            <TextInput
              style={styles.noteInput}
              placeholder="Add a note (visible to your team)…"
              placeholderTextColor={colors.textLight}
              value={noteDraft}
              onChangeText={setNoteDraft}
              multiline
            />
            <Pressable
              style={[
                styles.noteSubmit,
                (noteDraft.trim().length === 0 || addNote.isPending) &&
                  styles.noteSubmitDisabled,
              ]}
              disabled={noteDraft.trim().length === 0 || addNote.isPending || !chainId}
              onPress={() => {
                if (!chainId) return;
                addNote.mutate(
                  { chainId, body: noteDraft.trim() },
                  { onSuccess: () => setNoteDraft("") },
                );
              }}
            >
              {addNote.isPending ? (
                <ActivityIndicator size="small" color={colors.white} />
              ) : (
                <Ionicons name="send" size={16} color={colors.white} />
              )}
            </Pressable>
          </View>
          {(notes.data?.items ?? []).length === 0 ? (
            <Text style={styles.emptyHint}>
              No notes yet. Add the first observation above.
            </Text>
          ) : (
            (notes.data?.items ?? []).slice(0, 5).map((n) => (
              <View key={n.noteId} style={styles.noteCard}>
                <View style={styles.noteHeader}>
                  <Text style={styles.noteAuthor}>
                    {n.authorEmail ?? "system"}
                  </Text>
                  <Text style={styles.noteTime}>
                    {n.createdAt ? n.createdAt.slice(11, 19) : ""}
                  </Text>
                </View>
                <Text style={styles.noteBody}>{n.bodyMd}</Text>
              </View>
            ))
          )}
        </View>

        {/* Audit trail */}
        {(activity.data?.items ?? []).length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Activity</Text>
            {activity.data!.items.slice(0, 6).map((e) => (
              <View key={e.auditId} style={styles.activityRow}>
                <View style={styles.activityDot} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.activityKind}>
                    {(e.kind ?? "").replace(/_/g, " ")}
                  </Text>
                  <Text style={styles.activityMeta}>
                    {e.userEmail ?? "system"} · {e.at ? e.at.slice(11, 19) : ""}
                  </Text>
                  {(e.payload || e.note) && (
                    <Text style={styles.activityDetail} numberOfLines={2}>
                      {e.payload ?? e.note}
                    </Text>
                  )}
                </View>
              </View>
            ))}
          </View>
        )}

        {/* CKC progression timeline (existing) */}
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
  predictionsCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadows.card,
  },
  predictionRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  predictionMain: { flex: 1, gap: 4 },
  predictionStage: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.textPrimary,
  },
  predictionBar: {
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.bgSurface,
    overflow: "hidden",
  },
  predictionFill: { height: 6, borderRadius: 3 },
  predictionPct: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    width: 48,
    textAlign: "right",
  },
  playbookCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.xs,
    ...shadows.card,
  },
  playbookHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  playbookName: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
    flex: 1,
  },
  fallbackBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.full,
    backgroundColor: colors.warningBg,
  },
  fallbackText: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    color: colors.warning,
    letterSpacing: 0.6,
  },
  playbookDesc: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textBody,
    lineHeight: 18,
  },
  stepRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    paddingTop: 4,
  },
  stepIdx: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.primary,
    width: 14,
    textAlign: "center",
  },
  stepText: {
    flex: 1,
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textPrimary,
    lineHeight: 18,
  },
  noteInputRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: spacing.sm,
  },
  noteInput: {
    flex: 1,
    minHeight: 60,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textPrimary,
    textAlignVertical: "top",
  },
  noteSubmit: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  noteSubmitDisabled: { opacity: 0.5 },
  noteCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 4,
    ...shadows.card,
  },
  noteHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
  },
  noteAuthor: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.primary,
    letterSpacing: 0.6,
  },
  noteTime: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  noteBody: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textBody,
    lineHeight: 19,
  },
  activityRow: {
    flexDirection: "row",
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  activityDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.primary,
    marginTop: 6,
  },
  activityKind: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.textPrimary,
    textTransform: "capitalize",
  },
  activityMeta: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  activityDetail: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xs,
    color: colors.textBody,
    marginTop: 2,
  },
});
