import { View, Text, StyleSheet, Pressable } from "react-native";
import { colors, typography, radius, shadows, spacing } from "../lib/theme";
import type { AlertItem, Severity } from "../lib/api/hooks";

function severityConfig(sev: Severity) {
  switch (sev) {
    case "critical":
      return {
        border: colors.critical,
        label: "Critical Priority",
        labelText: colors.critical,
      };
    case "high":
      return {
        border: colors.critical,
        label: "High Priority",
        labelText: colors.critical,
      };
    case "medium":
      return {
        border: colors.warning,
        label: "Warning Event",
        labelText: colors.warning,
      };
    case "low":
      return {
        border: colors.info,
        label: "Low",
        labelText: colors.textMuted,
      };
    case "info":
    default:
      return {
        border: colors.primary,
        label: "Informational",
        labelText: colors.textMuted,
      };
  }
}

function timeAgo(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

function deriveTitle(alert: AlertItem): string {
  if (alert.decoderName && alert.ruleId) {
    return `${alert.decoderName} · ${alert.ruleId}`;
  }
  if (alert.decoderName) return alert.decoderName;
  if (alert.ruleId) return `Rule ${alert.ruleId}`;
  return "Unclassified event";
}

interface Props {
  alert: AlertItem;
  onAcknowledge?: (args: { alertId: string; occurredAt: string }) => void;
  acknowledging?: boolean;
}

export function AlertCard({ alert, onAcknowledge, acknowledging }: Props) {
  const cfg = severityConfig(alert.severity);
  const acknowledged = alert.acknowledgedAt !== null;
  const primaryTech =
    alert.mitreTechniques?.[0] ?? null;
  const primaryTactic = alert.mitreTactics?.[0] ?? null;

  return (
    <View style={[styles.card, { borderLeftColor: cfg.border }]}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={[styles.severityLabel, { color: cfg.labelText }]}>
          {cfg.label}
        </Text>
        <Text style={styles.time}>{timeAgo(alert.occurredAt)}</Text>
      </View>

      {/* Title */}
      <Text style={styles.title} numberOfLines={2}>
        {deriveTitle(alert)}
      </Text>

      {/* Description — full_log truncated */}
      {alert.fullLog ? (
        <Text style={styles.description} numberOfLines={3}>
          {alert.fullLog}
        </Text>
      ) : null}

      {/* Footer */}
      <View style={styles.footer}>
        {primaryTech ? (
          <View>
            <Text style={styles.mitreLabel}>MITRE Technique</Text>
            <Text style={styles.mitreValue} numberOfLines={1}>
              {primaryTech}
              {primaryTactic ? ` \u2022 ${primaryTactic}` : ""}
            </Text>
          </View>
        ) : null}
        <View style={styles.actions}>
          {!acknowledged ? (
            <Pressable
              style={styles.primaryBtn}
              disabled={!!acknowledging}
              onPress={() =>
                onAcknowledge?.({
                  alertId: alert.alertId,
                  occurredAt: alert.occurredAt,
                })
              }
            >
              <Text style={styles.primaryBtnText}>
                {acknowledging ? "…" : "ACKNOWLEDGE"}
              </Text>
            </Pressable>
          ) : (
            <View style={styles.ackedBadge}>
              <Text style={styles.ackedText}>ACKNOWLEDGED</Text>
            </View>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    borderTopRightRadius: radius.xl,
    borderLeftWidth: 4,
    padding: spacing.lg,
    ...shadows.card,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  severityLabel: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  time: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
  },
  title: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.textPrimary,
    lineHeight: typography.lineHeight.lg,
    marginBottom: spacing.sm,
  },
  description: {
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textBody,
    lineHeight: 22.75,
    marginBottom: spacing.md,
  },
  footer: { gap: spacing.sm },
  mitreLabel: {
    fontFamily: typography.family.headingRegular,
    fontSize: 9,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.9,
  },
  mitreValue: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.primary,
  },
  actions: {
    flexDirection: "row",
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  primaryBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
  },
  primaryBtnText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.primaryLight,
    letterSpacing: 0.6,
  },
  ackedBadge: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
    backgroundColor: colors.successBg,
  },
  ackedText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.success,
    letterSpacing: 0.8,
  },
});
