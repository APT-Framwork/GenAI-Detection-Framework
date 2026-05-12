/**
 * Compact 7-stage Cyber Kill-Chain visual.
 *
 * Renders the seven post-benign stages (Recon → Actions) as connected
 * pills with per-stage event counts. Each stage tints based on whether
 * it has activity in the current window: muted if zero, primary if some,
 * critical if it crossed an "active threat" threshold.
 *
 * Used on the dashboard (with `useAttackVector()`) and the analysis
 * detail page (with `useCkcProgression()`-derived counts).
 */

import { View, Text, StyleSheet, Pressable } from "react-native";

import { colors, radius, spacing, typography } from "../lib/theme";

export type KillChainStageInput = {
  ckcStage: number;
  ckcName: string;
  count: number;
};

interface Props {
  stages: KillChainStageInput[];
  highlightStage?: number | null;
  onPressStage?: (stage: KillChainStageInput) => void;
}

const STAGE_LABELS: Record<number, string> = {
  1: "Recon",
  2: "Weapon",
  3: "Deliver",
  4: "Exploit",
  5: "Install",
  6: "C2",
  7: "Actions",
};

export function KillChainStrip({ stages, highlightStage, onPressStage }: Props) {
  // Build a 1..7 lookup so missing stages render as zero-count cells.
  const byStage = new Map<number, KillChainStageInput>();
  for (const s of stages) byStage.set(s.ckcStage, s);

  return (
    <View style={styles.row}>
      {[1, 2, 3, 4, 5, 6, 7].map((stage, idx) => {
        const entry = byStage.get(stage) ?? {
          ckcStage: stage,
          ckcName: STAGE_LABELS[stage],
          count: 0,
        };
        const hot = entry.count >= 50;
        const has = entry.count > 0;
        const isCurrent = highlightStage === stage;
        const fg = hot
          ? colors.critical
          : has
            ? colors.primary
            : colors.textLight;
        const bg = hot
          ? colors.criticalBg
          : has
            ? colors.primaryLight
            : colors.bgSurface;
        const borderColor = isCurrent ? colors.primary : "transparent";

        return (
          <View key={stage} style={styles.cellWrap}>
            <Pressable
              disabled={!onPressStage}
              onPress={() => onPressStage?.(entry)}
              style={[
                styles.cell,
                { backgroundColor: bg, borderColor, borderWidth: isCurrent ? 2 : 0 },
              ]}
            >
              <Text style={[styles.count, { color: fg }]}>
                {entry.count > 999 ? "999+" : entry.count}
              </Text>
              <Text style={[styles.label, { color: fg }]}>
                {STAGE_LABELS[stage]}
              </Text>
            </Pressable>
            {idx < 6 ? (
              <View
                style={[
                  styles.connector,
                  { backgroundColor: has ? colors.primary : colors.border },
                ]}
              />
            ) : null}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 0,
  },
  cellWrap: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
  },
  cell: {
    flex: 1,
    alignItems: "center",
    paddingVertical: spacing.sm,
    paddingHorizontal: 2,
    borderRadius: radius.md,
    gap: 2,
  },
  count: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    letterSpacing: -0.4,
  },
  label: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    letterSpacing: 0.4,
  },
  connector: {
    width: 6,
    height: 1.5,
  },
});
