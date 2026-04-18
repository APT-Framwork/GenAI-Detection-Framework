import React, { Component, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { StrixApiError } from "../lib/api/client";
import { colors, radius, shadows, spacing, typography } from "../lib/theme";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Last-resort UI for crashes that escape a screen's local `useQuery`
 * error state. Resets via the "Try again" button — which remounts the
 * subtree, not just the boundary, so any corrupted state (e.g. a stale
 * mutation payload) clears with it.
 *
 * Intentionally avoids networking — we only render cached context
 * (StrixApiError details) plus generic fallback.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // In production, forward to crash reporter. For now just log.
    // eslint-disable-next-line no-console
    console.warn("[strix] fatal error", error);
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const title =
      error instanceof StrixApiError
        ? `${error.status} · ${error.message}`
        : "Something went wrong";
    const detail =
      error instanceof StrixApiError
        ? error.detail ?? error.code ?? "Unknown backend error."
        : error.message;

    return (
      <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
        <View style={styles.card}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.detail}>{detail}</Text>
          <Pressable style={styles.btn} onPress={this.reset}>
            <Text style={styles.btnText}>TRY AGAIN</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
  },
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.xl,
    gap: spacing.md,
    width: "100%",
    maxWidth: 420,
    ...shadows.card,
  },
  title: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.critical,
    letterSpacing: -0.3,
  },
  detail: {
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textBody,
    lineHeight: 22,
  },
  btn: {
    alignSelf: "flex-start",
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
    marginTop: spacing.sm,
  },
  btnText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.white,
    letterSpacing: 1,
  },
});
