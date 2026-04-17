import { View, Text, StyleSheet } from "react-native";
import { colors, typography, radius, shadows } from "../lib/theme";
import type { KPIMetric } from "../lib/mock-data";

interface Props {
  metric: KPIMetric;
  variant?: "surface" | "accent";
}

export function KPICard({ metric, variant = "surface" }: Props) {
  const bg = variant === "accent" ? colors.bgAccent : colors.bgSurface;

  return (
    <View style={[styles.card, { backgroundColor: bg }]}>
      <Text
        style={[
          styles.value,
          metric.color ? { color: metric.color } : undefined,
        ]}
      >
        {metric.value}
        {metric.unit && <Text style={styles.unit}>{metric.unit}</Text>}
      </Text>
      <Text style={styles.label}>{metric.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    alignItems: "center",
    padding: 12,
    borderRadius: radius.lg,
  },
  value: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.textPrimary,
    lineHeight: typography.lineHeight.xl,
  },
  unit: {
    fontSize: typography.size.md,
  },
  label: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    lineHeight: typography.lineHeight.xs,
  },
});
