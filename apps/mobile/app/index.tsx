import { useEffect, useRef } from "react";
import { View, Text, StyleSheet, Animated, Easing } from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, typography, spacing, radius } from "../lib/theme";
import { useUserStore } from "../stores/user-store";

export default function SplashEntry() {
  const router = useRouter();
  const status = useUserStore((s) => s.status);
  const isOnboarded = useUserStore((s) => s.isOnboarded);
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const progressAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 800,
      useNativeDriver: true,
    }).start();

    Animated.timing(progressAnim, {
      toValue: 1,
      duration: 2500,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, []);

  // Route once auth bootstrap resolves. If we're still `booting` after
  // the splash animation, we wait — a blank-screen guard is worth
  // keeping token validation correct.
  useEffect(() => {
    if (status === "booting") return;
    const timer = setTimeout(() => {
      if (status === "authed") {
        router.replace("/(tabs)/dashboard");
      } else if (isOnboarded) {
        router.replace("/(auth)/login");
      } else {
        router.replace("/(onboarding)/detection");
      }
    }, 2500);
    return () => clearTimeout(timer);
  }, [status, isOnboarded, router]);

  const progressWidth = progressAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ["0%", "66%"],
  });

  return (
    <SafeAreaView style={styles.container}>
      <Animated.View style={[styles.content, { opacity: fadeAnim }]}>
        {/* Owl Eye Logo */}
        <View style={styles.logoOuter}>
          <View style={styles.logoRing}>
            <View style={styles.logoInner}>
              <View style={styles.logoIris}>
                <View style={styles.logoPupil} />
                <View style={styles.logoPupilInner} />
              </View>
            </View>
          </View>
        </View>

        {/* Brand */}
        <Text style={styles.brand}>STRIX</Text>

        {/* Loading */}
        <View style={styles.loadingSection}>
          <Text style={styles.loadingText}>INITIALIZING CORE</Text>
          <View style={styles.progressTrack}>
            <Animated.View
              style={[styles.progressFill, { width: progressWidth }]}
            />
          </View>
        </View>

        {/* Footer metadata */}
        <View style={styles.footer}>
          <View>
            <Text style={styles.metaLabel}>Version</Text>
            <Text style={styles.metaValue}>SENTINEL_2.4.0</Text>
          </View>
          <View style={styles.footerRight}>
            <Text style={styles.metaLabel}>Status</Text>
            <View style={styles.statusRow}>
              <View style={styles.statusDot} />
              <Text style={styles.metaValue}>ENCRYPTED</Text>
            </View>
          </View>
        </View>
      </Animated.View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  content: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
  },
  logoOuter: {
    width: 192,
    height: 192,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing["2xl"],
  },
  logoRing: {
    width: 176,
    height: 176,
    borderRadius: 88,
    borderWidth: 2,
    borderColor: "rgba(128,182,195,0.3)",
    alignItems: "center",
    justifyContent: "center",
  },
  logoInner: {
    width: 128,
    height: 128,
    borderRadius: 64,
    borderWidth: 1,
    borderColor: "rgba(128,182,195,0.3)",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  logoIris: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 25 },
    shadowOpacity: 0.25,
    shadowRadius: 50,
    elevation: 10,
  },
  logoPupil: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "rgba(255,255,255,0.3)",
    alignItems: "center",
    justifyContent: "center",
  },
  logoPupilInner: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: colors.primaryDark,
  },
  brand: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["5xl"],
    color: colors.primary,
    letterSpacing: -1.8,
    textAlign: "center",
    marginBottom: spacing.md,
  },
  loadingSection: {
    alignItems: "center",
    gap: spacing.sm,
  },
  loadingText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.textMuted,
    letterSpacing: typography.tracking.widest,
    textTransform: "uppercase",
  },
  progressTrack: {
    width: 128,
    height: 2,
    backgroundColor: colors.bgSurface,
    borderRadius: radius.full,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    backgroundColor: colors.primary,
    borderRadius: radius.full,
  },
  footer: {
    position: "absolute",
    bottom: spacing["2xl"],
    left: spacing.xl,
    right: spacing.xl,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-end",
  },
  footerRight: {
    alignItems: "flex-end",
  },
  metaLabel: {
    fontFamily: typography.family.headingRegular,
    fontSize: typography.size.xs,
    color: colors.textLight,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  metaValue: {
    fontFamily: typography.family.headingMedium,
    fontSize: typography.size.sm,
    color: colors.textPrimary,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.primary,
  },
});
