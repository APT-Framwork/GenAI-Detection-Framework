/**
 * Top MITRE ATT&CK tactics strip — horizontal chip row showing the most
 * active tactics in the current window with technique counts.
 *
 * Sourced from `useMitreCoverage()`. We surface up to 6 tactics ordered
 * by totalCount desc; the analyst can scroll to see the rest.
 */

import { ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, typography } from "../lib/theme";
import type { MitreTactic } from "../lib/api/hooks";

interface Props {
  tactics: MitreTactic[];
  limit?: number;
}

export function MitreStrip({ tactics, limit = 6 }: Props) {
  const top = [...tactics]
    .filter((t) => (t.columnTotal ?? 0) > 0)
    .sort((a, b) => (b.columnTotal ?? 0) - (a.columnTotal ?? 0))
    .slice(0, limit);

  if (top.length === 0) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyText}>No MITRE activity in window</Text>
      </View>
    );
  }

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
    >
      {top.map((t) => {
        const total = t.columnTotal ?? 0;
        const techniques = t.techniques ?? [];
        return (
          <View key={t.tacticId} style={styles.chip}>
            <Text style={styles.tactic} numberOfLines={1}>
              {t.tacticName}
            </Text>
            <View style={styles.metaRow}>
              <Text style={styles.tacticId}>{t.tacticId}</Text>
              <Text style={styles.dot}>·</Text>
              <Text style={styles.count}>
                {total} {total === 1 ? "event" : "events"}
              </Text>
            </View>
            <Text style={styles.techCount}>
              {techniques.length} technique{techniques.length === 1 ? "" : "s"}
            </Text>
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: { gap: spacing.sm, paddingRight: spacing.md },
  chip: {
    backgroundColor: colors.bgCard,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    minWidth: 140,
    gap: 2,
  },
  tactic: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 4 },
  tacticId: {
    fontFamily: typography.family.mono,
    fontSize: typography.size.xs,
    color: colors.primary,
  },
  dot: { color: colors.textMuted, fontSize: typography.size.xs },
  count: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xs,
    color: colors.textBody,
  },
  techCount: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    color: colors.textMuted,
    letterSpacing: typography.tracking.wide,
    textTransform: "uppercase",
  },
  empty: {
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  emptyText: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
});
