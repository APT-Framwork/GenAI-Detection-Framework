import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";

export default function IntelligenceScreen() {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* Progress dots */}
        <View style={styles.progressRow}>
          <View style={[styles.progressDot, { width: 32, backgroundColor: colors.primary }]} />
          <View style={[styles.progressDot, { width: 32, backgroundColor: colors.primary }]} />
          <View style={styles.progressDot} />
          <View style={styles.progressDot} />
        </View>

        {/* Icon */}
        <View style={styles.iconContainer}>
          <View style={styles.iconCircle}>
            <Text style={styles.iconText}>{"{ }"}</Text>
          </View>
        </View>

        {/* Title */}
        <Text style={styles.title}>
          Predictive{"\n"}Intelligence
        </Text>

        {/* Description */}
        <Text style={styles.description}>
          CAVIX, driven by the STRIX RL agent, monitors patterns to neutralize threats before they materialize.
        </Text>

        {/* Feature cards */}
        <View style={styles.featureCard}>
          <View style={styles.featureIcon}>
            <Text style={styles.featureEmoji}>{"*"}</Text>
          </View>
          <View style={styles.featureText}>
            <Text style={styles.featureTitle}>Neural Analysis</Text>
            <Text style={styles.featureDesc}>
              Real-time behavior modeling across all network nodes.
            </Text>
          </View>
        </View>

        <View style={styles.featureCard}>
          <View style={[styles.featureIcon, { backgroundColor: "transparent" }]}>
            <Text style={styles.featureEmoji}>{"@"}</Text>
          </View>
          <View style={styles.featureText}>
            <Text style={styles.featureTitle}>Proactive Defense</Text>
            <Text style={styles.featureDesc}>
              Automated containment of identified suspicious heuristics.
            </Text>
          </View>
        </View>

        {/* Neural network visual placeholder */}
        <View style={styles.visualPlaceholder}>
          <View style={styles.visualGradient} />
          <Text style={styles.visualLabel}>Neural Mesh Active</Text>
        </View>
      </ScrollView>

      {/* Footer */}
      <View style={styles.footer}>
        <Pressable
          style={styles.nextButton}
          onPress={() => router.push("/(onboarding)/orchestration")}
        >
          <Text style={styles.nextButtonText}>NEXT</Text>
          <Text style={styles.nextArrow}>{"\u2192"}</Text>
        </Pressable>
        <Text style={styles.stepLabel}>Step 2 of 4 {"\u2022"} Technical Onboarding</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing["2xl"],
    // Footer is position:absolute (~120pt) — leave clearance so the
    // "Neural Mesh Active" pill at the end of the visual doesn't get
    // tucked underneath the NEXT button on short viewports.
    paddingBottom: 280,
  },
  progressRow: {
    flexDirection: "row",
    gap: spacing.sm,
    marginBottom: spacing["2xl"],
  },
  progressDot: {
    height: 4,
    width: 32,
    borderRadius: radius.full,
    backgroundColor: "rgba(128,182,195,0.3)",
  },
  iconContainer: {
    marginBottom: spacing["2xl"],
  },
  iconCircle: {
    width: 62,
    height: 62,
    borderRadius: radius.xl,
    backgroundColor: colors.bgAccent,
    alignItems: "center",
    justifyContent: "center",
  },
  iconText: {
    fontFamily: typography.family.heading,
    fontSize: 20,
    color: colors.primary,
  },
  title: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["5xl"],
    color: colors.primary,
    letterSpacing: typography.tracking.tight,
    lineHeight: 36,
    marginBottom: spacing.md,
  },
  description: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xl,
    color: colors.textBody,
    lineHeight: 29.25,
    maxWidth: 280,
    marginBottom: spacing["2xl"],
  },
  featureCard: {
    flexDirection: "row",
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.lg,
    ...shadows.card,
    backgroundColor: "rgba(255,255,255,0.01)",
    marginBottom: spacing.md,
  },
  featureIcon: {
    width: 38,
    height: 38,
    borderRadius: radius.lg,
    backgroundColor: "rgba(135,237,246,0.2)",
    alignItems: "center",
    justifyContent: "center",
  },
  featureEmoji: {
    fontSize: 18,
    color: colors.primary,
  },
  featureText: {
    flex: 1,
  },
  featureTitle: {
    fontFamily: typography.family.headingMedium,
    fontSize: typography.size.lg,
    color: colors.textPrimary,
    lineHeight: typography.lineHeight.lg,
  },
  featureDesc: {
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textBody,
    lineHeight: 20,
  },
  visualPlaceholder: {
    height: 192,
    borderRadius: radius.xl,
    backgroundColor: colors.bgSurface,
    overflow: "hidden",
    justifyContent: "flex-end",
    marginTop: spacing.md,
  },
  visualGradient: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(135,237,246,0.15)",
  },
  visualLabel: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 1,
    padding: spacing.md,
  },
  footer: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    paddingHorizontal: spacing.lg,
    paddingBottom: 40,
    paddingTop: spacing.md,
    backgroundColor: "rgba(255,255,255,0.7)",
    alignItems: "center",
    gap: spacing.md,
  },
  nextButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    backgroundColor: colors.primary,
    borderRadius: radius.full,
    paddingVertical: spacing.md,
    width: "100%",
    ...shadows.button,
  },
  nextButtonText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.primaryLight,
    letterSpacing: 1.4,
  },
  nextArrow: {
    fontSize: 14,
    color: colors.primaryLight,
  },
  stepLabel: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 2,
  },
});
