import { View, Text, StyleSheet, Pressable } from "react-native";
import { colors, typography, radius, shadows, spacing } from "../lib/theme";
import type { Alert } from "../lib/mock-data";

const severityColors: Record<string, { border: string; label: string; labelText: string }> = {
  critical: { border: colors.critical, label: "Critical Priority", labelText: colors.critical },
  warning: { border: colors.warning, label: "Warning Event", labelText: colors.warning },
  info: { border: colors.info, label: "System Update", labelText: colors.textMuted },
  update: { border: colors.primary, label: "System Update", labelText: colors.textMuted },
};

interface Props {
  alert: Alert;
  onAcknowledge?: (id: string) => void;
}

export function AlertCard({ alert, onAcknowledge }: Props) {
  const config = severityColors[alert.severity] ?? severityColors.info;

  return (
    <View style={[styles.card, { borderLeftColor: config.border }]}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={[styles.severityLabel, { color: config.labelText }]}>
          {config.label}
        </Text>
        <Text style={styles.time}>{alert.timeAgo}</Text>
      </View>

      {/* Title */}
      <Text style={styles.title}>{alert.title}</Text>

      {/* Description */}
      <Text style={styles.description}>{alert.description}</Text>

      {/* Footer */}
      <View style={styles.footer}>
        {alert.mitreTechnique && (
          <View>
            <Text style={styles.mitreLabel}>MITRE Technique</Text>
            <Text style={styles.mitreValue}>
              {alert.mitreTechnique} {"\u2022"} {alert.mitreLabel}
            </Text>
          </View>
        )}
        <View style={styles.actions}>
          {!alert.acknowledged && (
            <Pressable
              style={styles.primaryBtn}
              onPress={() => onAcknowledge?.(alert.id)}
            >
              <Text style={styles.primaryBtnText}>
                {alert.severity === "critical" ? "LOCK SYSTEM" : "ACKNOWLEDGE"}
              </Text>
            </Pressable>
          )}
          <Pressable style={styles.secondaryBtn}>
            <Text style={styles.secondaryBtnText}>
              {alert.severity === "critical" ? "INVESTIGATE" : "DISMISS"}
            </Text>
          </Pressable>
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
  footer: {
    gap: spacing.sm,
  },
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
  secondaryBtn: {
    backgroundColor: colors.bgSurface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
  },
  secondaryBtnText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.primary,
    letterSpacing: 0.6,
  },
});
