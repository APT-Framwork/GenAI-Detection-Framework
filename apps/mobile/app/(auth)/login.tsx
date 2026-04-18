import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { StrixApiError } from "../../lib/api/client";
import { colors, radius, shadows, spacing, typography } from "../../lib/theme";
import { useUserStore } from "../../stores/user-store";

export default function LoginScreen() {
  const router = useRouter();
  const login = useUserStore((s) => s.login);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const disabled = busy || !email.trim() || !password;

  async function submit() {
    if (disabled) return;
    setBusy(true);
    setError(null);
    try {
      await login(email.trim().toLowerCase(), password);
      router.replace("/(tabs)/dashboard");
    } catch (exc) {
      if (exc instanceof StrixApiError) {
        if (exc.status === 401) {
          setError("Invalid email or password.");
        } else if (exc.status >= 500) {
          setError("Server unavailable. Try again in a moment.");
        } else {
          setError(exc.message || "Sign-in failed.");
        }
      } else {
        setError("Network error — check the API is reachable.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          {/* Logo + brand */}
          <View style={styles.brandBlock}>
            <View style={styles.logoRing}>
              <View style={styles.logoInner}>
                <View style={styles.logoIris}>
                  <View style={styles.logoPupil} />
                </View>
              </View>
            </View>
            <Text style={styles.brand}>STRIX</Text>
            <Text style={styles.tagline}>SENTINEL CONSOLE</Text>
          </View>

          {/* Card */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Sign in</Text>
            <Text style={styles.cardSub}>
              Use your SOC operator credentials.
            </Text>

            {/* Email */}
            <View style={styles.field}>
              <Text style={styles.label}>EMAIL</Text>
              <View style={styles.inputWrap}>
                <Ionicons
                  name="mail-outline"
                  size={18}
                  color={colors.textMuted}
                />
                <TextInput
                  style={styles.input}
                  placeholder="operator@strix.local"
                  placeholderTextColor={colors.textLight}
                  autoCapitalize="none"
                  autoComplete="email"
                  keyboardType="email-address"
                  textContentType="emailAddress"
                  value={email}
                  onChangeText={setEmail}
                  editable={!busy}
                  returnKeyType="next"
                />
              </View>
            </View>

            {/* Password */}
            <View style={styles.field}>
              <Text style={styles.label}>PASSWORD</Text>
              <View style={styles.inputWrap}>
                <Ionicons
                  name="lock-closed-outline"
                  size={18}
                  color={colors.textMuted}
                />
                <TextInput
                  style={styles.input}
                  placeholder="••••••••••"
                  placeholderTextColor={colors.textLight}
                  secureTextEntry={!showPw}
                  autoCapitalize="none"
                  autoComplete="password"
                  textContentType="password"
                  value={password}
                  onChangeText={setPassword}
                  editable={!busy}
                  returnKeyType="go"
                  onSubmitEditing={submit}
                />
                <Pressable
                  onPress={() => setShowPw((v) => !v)}
                  hitSlop={8}
                  disabled={busy}
                >
                  <Ionicons
                    name={showPw ? "eye-off-outline" : "eye-outline"}
                    size={18}
                    color={colors.textMuted}
                  />
                </Pressable>
              </View>
            </View>

            {error ? (
              <View style={styles.errorBox}>
                <Ionicons name="alert-circle" size={16} color={colors.critical} />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            ) : null}

            {/* Submit */}
            <Pressable
              onPress={submit}
              disabled={disabled}
              style={({ pressed }) => [
                styles.btn,
                disabled && styles.btnDisabled,
                pressed && !disabled && styles.btnPressed,
              ]}
            >
              {busy ? (
                <ActivityIndicator color={colors.white} />
              ) : (
                <>
                  <Text style={styles.btnText}>SIGN IN</Text>
                  <Ionicons name="arrow-forward" size={16} color={colors.white} />
                </>
              )}
            </Pressable>
          </View>

          <Pressable
            style={styles.registerLink}
            onPress={() => router.push("/(auth)/register")}
            hitSlop={10}
          >
            <Text style={styles.registerText}>
              Need an account? <Text style={styles.registerCta}>Create one</Text>
            </Text>
          </Pressable>

          <Text style={styles.footer}>
            Encrypted channel · Bearer token authentication
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  scroll: {
    flexGrow: 1,
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xl,
    justifyContent: "center",
  },
  brandBlock: {
    alignItems: "center",
    marginBottom: spacing["2xl"],
  },
  logoRing: {
    width: 88,
    height: 88,
    borderRadius: 44,
    borderWidth: 2,
    borderColor: "rgba(128,182,195,0.3)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.md,
  },
  logoInner: {
    width: 64,
    height: 64,
    borderRadius: 32,
    borderWidth: 1,
    borderColor: "rgba(128,182,195,0.3)",
    alignItems: "center",
    justifyContent: "center",
  },
  logoIris: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  logoPupil: {
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: colors.primaryDark,
  },
  brand: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["4xl"],
    color: colors.primary,
    letterSpacing: -1.6,
  },
  tagline: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: typography.tracking.widest,
    marginTop: spacing.xs,
  },
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.xl,
    gap: spacing.md,
    ...shadows.card,
  },
  cardTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["2xl"],
    color: colors.textPrimary,
    letterSpacing: typography.tracking.tight,
  },
  cardSub: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  field: { gap: 6 },
  label: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: 1,
  },
  inputWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.bgSurface,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: colors.borderMedium,
  },
  input: {
    flex: 1,
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textPrimary,
    paddingVertical: 0,
  },
  errorBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.criticalBg,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
  },
  errorText: {
    flex: 1,
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.critical,
  },
  btn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    backgroundColor: colors.primary,
    borderRadius: radius.full,
    paddingVertical: 14,
    marginTop: spacing.sm,
  },
  btnDisabled: {
    opacity: 0.5,
  },
  btnPressed: {
    opacity: 0.85,
  },
  btnText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.white,
    letterSpacing: 1.5,
  },
  registerLink: {
    alignItems: "center",
    paddingVertical: spacing.md,
    marginTop: spacing.sm,
  },
  registerText: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  registerCta: {
    fontFamily: typography.family.heading,
    color: colors.primary,
    letterSpacing: 0.4,
  },
  footer: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textLight,
    textAlign: "center",
    marginTop: spacing.sm,
    letterSpacing: 0.5,
  },
});
