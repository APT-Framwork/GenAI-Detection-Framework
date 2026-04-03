import { View, Text, StyleSheet, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";

export default function DetectionScreen() {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={styles.logoIcon}>
            <View style={styles.logoPupil} />
          </View>
          <Text style={styles.headerTitle}>SENTINEL</Text>
        </View>
        <View style={styles.avatar} />
      </View>

      {/* Progress */}
      <View style={styles.progressRow}>
        <View style={[styles.progressDot, styles.progressDotActive]} />
        <View style={styles.progressDot} />
        <View style={styles.progressDot} />
      </View>

      {/* Hero Visual */}
      <View style={styles.heroCard}>
        <View style={styles.heroVisual}>
          <View style={styles.heroCornerTR} />
          <View style={styles.heroCornerBL} />
          <View style={styles.heroEye}>
            <View style={styles.heroEyeOuter}>
              <View style={styles.heroEyeInner}>
                <View style={styles.heroEyePupil} />
              </View>
            </View>
          </View>
        </View>
      </View>

      {/* Text Content */}
      <View style={styles.textContent}>
        <Text style={styles.title}>
          Vigilant{"\n"}Detection
        </Text>
        <Text style={styles.description}>
          Continuous perimeter scanning with AI-driven threat recognition.{" "}
          <Text style={styles.descBold}>STRIX</Text> never blinks.
        </Text>
        <View style={styles.statusChip}>
          <View style={styles.chipDot} />
          <Text style={styles.chipText}>SYSTEM READY</Text>
        </View>
      </View>

      {/* Bottom Action */}
      <View style={styles.footer}>
        <Pressable
          style={styles.nextButton}
          onPress={() => router.push("/(onboarding)/intelligence")}
        >
          <Text style={styles.nextButtonText}>NEXT</Text>
          <Text style={styles.nextArrow}>{"\u2192"}</Text>
        </Pressable>
        <Pressable onPress={() => router.replace("/(tabs)/dashboard")}>
          <Text style={styles.skipText}>SKIP INTRODUCTION</Text>
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
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    height: 64,
  },
  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  logoIcon: {
    width: 16,
    height: 20,
    backgroundColor: colors.primary,
    borderRadius: 4,
    alignItems: "center",
    justifyContent: "center",
  },
  logoPupil: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.primaryLight,
  },
  headerTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["2xl"],
    color: colors.primary,
    letterSpacing: -1,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: radius.full,
    backgroundColor: colors.bgAccentLight,
  },
  progressRow: {
    flexDirection: "row",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing["2xl"],
  },
  progressDot: {
    height: 6,
    width: 16,
    borderRadius: radius.full,
    backgroundColor: "rgba(128,182,195,0.3)",
  },
  progressDotActive: {
    width: 32,
    backgroundColor: colors.primary,
  },
  heroCard: {
    marginHorizontal: spacing.lg,
    backgroundColor: colors.bgCard,
    borderRadius: radius.xl,
    padding: spacing["2xl"],
    alignItems: "center",
    justifyContent: "center",
    ...shadows.card,
  },
  heroVisual: {
    width: 192,
    height: 192,
    alignItems: "center",
    justifyContent: "center",
  },
  heroCornerTR: {
    position: "absolute",
    top: 0,
    right: 0,
    width: 48,
    height: 48,
    borderTopWidth: 2,
    borderRightWidth: 2,
    borderColor: "rgba(0,102,109,0.3)",
    borderTopRightRadius: radius.xl,
  },
  heroCornerBL: {
    position: "absolute",
    bottom: 0,
    left: 0,
    width: 48,
    height: 48,
    borderBottomWidth: 2,
    borderLeftWidth: 2,
    borderColor: "rgba(0,102,109,0.3)",
    borderBottomLeftRadius: radius.xl,
  },
  heroEye: {
    width: 132,
    height: 111,
    alignItems: "center",
    justifyContent: "center",
  },
  heroEyeOuter: {
    width: 96,
    height: 96,
    borderRadius: 48,
    borderWidth: 2,
    borderColor: "rgba(128,182,195,0.3)",
    alignItems: "center",
    justifyContent: "center",
  },
  heroEyeInner: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 6,
  },
  heroEyePupil: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: "rgba(255,255,255,0.3)",
  },
  textContent: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing["2xl"],
    gap: spacing.lg,
  },
  title: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["5xl"],
    color: colors.primary,
    letterSpacing: typography.tracking.tight,
    lineHeight: 40,
  },
  description: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xl,
    color: colors.textBody,
    lineHeight: 29.25,
  },
  descBold: {
    fontFamily: typography.family.bodySemiBold,
    color: colors.primary,
  },
  statusChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.bgSurface,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 13,
    paddingVertical: 5,
    borderRadius: radius.full,
    alignSelf: "flex-start",
  },
  chipDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.primary,
  },
  chipText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.primary,
    textTransform: "uppercase",
    letterSpacing: 1,
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
    gap: 12,
    backgroundColor: colors.primary,
    borderRadius: radius.lg,
    paddingVertical: 20,
    width: "100%",
    ...shadows.button,
  },
  nextButtonText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.primaryLight,
    letterSpacing: 0.9,
  },
  nextArrow: {
    fontSize: 18,
    color: colors.primaryLight,
  },
  skipText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.textMuted,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
});
