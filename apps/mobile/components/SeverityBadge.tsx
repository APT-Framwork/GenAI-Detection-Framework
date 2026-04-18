import { View, Text, StyleSheet } from "react-native";
import { colors, typography, radius } from "../lib/theme";
import type { Severity } from "../lib/api/hooks";

const severityConfig: Record<
  Severity,
  { bg: string; text: string; label: string; dot: string }
> = {
  critical: {
    bg: colors.criticalBg,
    text: colors.critical,
    label: "Critical",
    dot: colors.critical,
  },
  high: {
    bg: colors.criticalBg,
    text: colors.critical,
    label: "High",
    dot: colors.critical,
  },
  medium: {
    bg: colors.warningBg,
    text: colors.warning,
    label: "Medium",
    dot: colors.warning,
  },
  low: {
    bg: colors.infoBg,
    text: colors.info,
    label: "Low",
    dot: colors.info,
  },
  info: {
    bg: colors.successBg,
    text: colors.primary,
    label: "Info",
    dot: colors.primary,
  },
};

interface Props {
  severity: Severity;
  showDot?: boolean;
}

export function SeverityBadge({ severity, showDot = true }: Props) {
  const config = severityConfig[severity];
  return (
    <View style={[styles.container, { backgroundColor: config.bg }]}>
      {showDot && (
        <View style={[styles.dot, { backgroundColor: config.dot }]} />
      )}
      <Text style={[styles.label, { color: config.text }]}>
        {config.label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.full,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: radius.full,
  },
  label: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
});
