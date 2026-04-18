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

export default function RegisterScreen() {
  const router = useRouter();
  const register = useUserStore((s) => s.register);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [designation, setDesignation] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const passwordTooShort = password.length > 0 && password.length < 8;
  const disabled =
    busy || !email.trim() || password.length < 8;

  async function submit() {
    if (disabled) return;
    setBusy(true);
    setError(null);
    try {
      await register(
        email.trim().toLowerCase(),
        password,
        designation.trim() || undefined,
      );
      router.replace("/(tabs)/dashboard");
    } catch (exc) {
      if (exc instanceof StrixApiError) {
        if (exc.status === 409) {
          setError("That email is already registered.");
        } else if (exc.status === 422) {
          setError(exc.detail ?? "Invalid email or password.");
        } else if (exc.status >= 500) {
          setError("Server unavailable. Try again in a moment.");
        } else {
          setError(exc.message || "Registration failed.");
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
          {/* Back */}
          <Pressable
            onPress={() => router.back()}
            style={styles.backBtn}
            hitSlop={10}
          >
            <Ionicons name="chevron-back" size={22} color={colors.primary} />
            <Text style={styles.backText}>Sign in</Text>
          </Pressable>

          {/* Brand */}
          <View style={styles.brandBlock}>
            <Text style={styles.brand}>Create account</Text>
            <Text style={styles.tagline}>
              New analysts start with the `analyst` role.
            </Text>
          </View>

          {/* Card */}
          <View style={styles.card}>
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
                  placeholder="≥ 8 characters"
                  placeholderTextColor={colors.textLight}
                  secureTextEntry={!showPw}
                  autoCapitalize="none"
                  autoComplete="new-password"
                  textContentType="newPassword"
                  value={password}
                  onChangeText={setPassword}
                  editable={!busy}
                  returnKeyType="next"
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
              {passwordTooShort ? (
                <Text style={styles.hint}>At least 8 characters.</Text>
              ) : null}
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>CALL SIGN (optional)</Text>
              <View style={styles.inputWrap}>
                <Ionicons
                  name="ribbon-outline"
                  size={18}
                  color={colors.textMuted}
                />
                <TextInput
                  style={styles.input}
                  placeholder="OP-ALPHA-7"
                  placeholderTextColor={colors.textLight}
                  autoCapitalize="characters"
                  autoCorrect={false}
                  value={designation}
                  onChangeText={setDesignation}
                  editable={!busy}
                  returnKeyType="go"
                  onSubmitEditing={submit}
                />
              </View>
            </View>

            {error ? (
              <View style={styles.errorBox}>
                <Ionicons
                  name="alert-circle"
                  size={16}
                  color={colors.critical}
                />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            ) : null}

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
                  <Text style={styles.btnText}>CREATE ACCOUNT</Text>
                  <Ionicons
                    name="arrow-forward"
                    size={16}
                    color={colors.white}
                  />
                </>
              )}
            </Pressable>
          </View>

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
  },
  backBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  backText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.primary,
    letterSpacing: 0.5,
  },
  brandBlock: {
    gap: spacing.xs,
    marginBottom: spacing.xl,
  },
  brand: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["4xl"],
    color: colors.textPrimary,
    letterSpacing: -1.4,
  },
  tagline: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
  },
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.xl,
    gap: spacing.md,
    ...shadows.card,
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
  hint: {
    fontFamily: typography.family.body,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    paddingHorizontal: spacing.xs,
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
  btnDisabled: { opacity: 0.5 },
  btnPressed: { opacity: 0.85 },
  btnText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.white,
    letterSpacing: 1.5,
  },
  footer: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textLight,
    textAlign: "center",
    marginTop: spacing.lg,
    letterSpacing: 0.5,
  },
});
