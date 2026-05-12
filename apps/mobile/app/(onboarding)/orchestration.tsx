import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useUserStore } from "../../stores/user-store";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";
import { CavixLogo } from "../../components/CavixLogo";

export default function OrchestrationScreen() {
  const router = useRouter();
  const setOnboarded = useUserStore((s) => s.setOnboarded);

  const handleGetStarted = () => {
    setOnboarded(true);
    router.replace("/(auth)/login");
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <CavixLogo width={92} />
        </View>

        {/* Hero visual */}
        <View style={styles.heroContainer}>
          <View style={styles.heroRings}>
            <View style={styles.ring1} />
            <View style={styles.ring2} />
            <View style={styles.ring3} />
            <View style={styles.heroCenterBox}>
              <View style={styles.heroShield}>
                <Text style={styles.shieldIcon}>{"\u2665"}</Text>
              </View>
              {/* Automation lines */}
              <View style={styles.autoLinesTop}>
                <View style={[styles.autoLine, { width: 48, opacity: 0.4 }]} />
                <View style={[styles.autoLine, { width: 32, opacity: 0.2 }]} />
              </View>
              <View style={styles.autoLinesBottom}>
                <View style={[styles.autoLine, { width: 32, opacity: 0.2 }]} />
                <View style={[styles.autoLine, { width: 48, opacity: 0.4 }]} />
              </View>
            </View>
            {/* Floating labels */}
            <View style={styles.floatingActive}>
              <View style={[styles.floatingDot, { backgroundColor: colors.bgAccent }]} />
              <Text style={styles.floatingText}>ACTIVE</Text>
            </View>
            <View style={styles.floatingSyncing}>
              <View style={[styles.floatingDot, { backgroundColor: "#dcb8ff" }]} />
              <Text style={styles.floatingText}>SYNCING</Text>
            </View>
          </View>
        </View>

        {/* Phase label */}
        <View style={styles.phaseRow}>
          <View style={styles.phaseLine} />
          <Text style={styles.phaseText}>PHASE 03</Text>
        </View>

        {/* Title */}
        <Text style={styles.title}>
          Tactical{"\n"}
          <Text style={{ color: colors.primary }}>Orchestration</Text>
        </Text>

        {/* Description */}
        <Text style={styles.description}>
          Experience the precision of the Nocturnal Sentinel. Our AI-driven
          engine automates threat neutralization before the breach even occurs.
        </Text>

        {/* Feature grid */}
        <View style={styles.featureGrid}>
          <View style={[styles.featureBox, { borderLeftColor: "rgba(0,102,109,0.3)" }]}>
            <Text style={styles.featureTitle}>AUTO-RESPONSE</Text>
            <Text style={styles.featureDesc}>Sub-second reaction</Text>
          </View>
          <View style={[styles.featureBox, { borderLeftColor: "rgba(220,184,255,0.3)" }]}>
            <Text style={styles.featureTitle}>VIGILANCE</Text>
            <Text style={styles.featureDesc}>24/7 Deep Scan</Text>
          </View>
        </View>
      </ScrollView>

      {/* CTA */}
      <View style={styles.footer}>
        <Pressable style={styles.getStartedBtn} onPress={handleGetStarted}>
          <Text style={styles.getStartedText}>GET STARTED</Text>
          <Text style={styles.getStartedArrow}>{"\u2192"}</Text>
        </Pressable>
        <Pressable onPress={handleGetStarted}>
          <Text style={styles.advancedText}>ADVANCED SETUP</Text>
        </Pressable>
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
    paddingBottom: 200,
  },
  header: {
    paddingVertical: spacing.md,
  },
  headerBrand: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.primary,
    letterSpacing: typography.tracking.ultra,
    textTransform: "uppercase",
  },
  heroContainer: {
    alignItems: "center",
    paddingVertical: spacing.xl,
  },
  heroRings: {
    width: 256,
    height: 256,
    alignItems: "center",
    justifyContent: "center",
  },
  ring1: {
    ...StyleSheet.absoluteFillObject,
    borderWidth: 1,
    borderColor: "rgba(0,102,109,0.1)",
    borderRadius: 12,
  },
  ring2: {
    position: "absolute",
    top: 16,
    left: 16,
    right: 16,
    bottom: 16,
    borderWidth: 1,
    borderColor: "rgba(0,102,109,0.05)",
    borderRadius: 12,
  },
  ring3: {
    position: "absolute",
    top: 48,
    left: 48,
    right: 48,
    bottom: 48,
    borderWidth: 1,
    borderColor: "rgba(0,102,109,0.2)",
    borderRadius: 12,
  },
  heroCenterBox: {
    width: 108,
    height: 108,
    borderRadius: 12,
    backgroundColor: colors.bgCard,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    ...shadows.card,
  },
  heroShield: {
    width: 48,
    height: 48,
    borderRadius: radius.lg,
    backgroundColor: colors.bgAccent,
    alignItems: "center",
    justifyContent: "center",
  },
  shieldIcon: {
    fontSize: 24,
    color: colors.primary,
  },
  autoLinesTop: {
    position: "absolute",
    top: -16,
    right: -16,
    gap: 4,
  },
  autoLinesBottom: {
    position: "absolute",
    bottom: -16,
    left: -16,
    alignItems: "flex-end",
    gap: 4,
  },
  autoLine: {
    height: 4,
    backgroundColor: colors.bgAccent,
    borderRadius: 2,
  },
  floatingActive: {
    position: "absolute",
    top: 16,
    right: 32,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.bgCard,
    borderLeftWidth: 2,
    borderLeftColor: colors.primary,
    borderRadius: radius.sm,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  floatingSyncing: {
    position: "absolute",
    bottom: 48,
    left: 0,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.bgCard,
    borderLeftWidth: 2,
    borderLeftColor: "rgba(220,184,255,0.5)",
    borderRadius: radius.sm,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  floatingDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  floatingText: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textPrimary,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  phaseRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  phaseLine: {
    width: 32,
    height: 2,
    backgroundColor: colors.primary,
  },
  phaseText: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.sm,
    color: colors.primary,
    letterSpacing: typography.tracking.ultra,
    textTransform: "uppercase",
  },
  title: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["5xl"],
    color: colors.textPrimary,
    letterSpacing: typography.tracking.tight,
    lineHeight: 45,
    marginBottom: spacing.lg,
  },
  description: {
    fontFamily: typography.family.body,
    fontSize: typography.size.lg,
    color: colors.textBody,
    lineHeight: 26,
    marginBottom: spacing.lg,
  },
  featureGrid: {
    flexDirection: "row",
    gap: spacing.md,
  },
  featureBox: {
    flex: 1,
    backgroundColor: colors.bgCard,
    borderLeftWidth: 2,
    borderRadius: radius.sm,
    padding: spacing.md,
    ...shadows.card,
  },
  featureTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.textPrimary,
    letterSpacing: 1.2,
    textTransform: "uppercase",
    marginBottom: 4,
  },
  featureDesc: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xs,
    color: colors.textBody,
  },
  footer: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    paddingHorizontal: spacing.xl,
    paddingBottom: 40,
    paddingTop: spacing.md,
    backgroundColor: "rgba(231,250,255,0.9)",
    alignItems: "center",
    gap: spacing.sm,
  },
  getStartedBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    backgroundColor: colors.primary,
    borderRadius: radius.full,
    paddingVertical: spacing.md,
    width: "100%",
    ...shadows.button,
  },
  getStartedText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.primaryLight,
    letterSpacing: 2.8,
    textTransform: "uppercase",
  },
  getStartedArrow: {
    fontSize: 16,
    color: colors.primaryLight,
  },
  advancedText: {
    fontFamily: typography.family.headingMedium,
    fontSize: typography.size.sm,
    color: colors.textBody,
    letterSpacing: 1.2,
    textTransform: "uppercase",
    paddingVertical: spacing.md,
  },
});
