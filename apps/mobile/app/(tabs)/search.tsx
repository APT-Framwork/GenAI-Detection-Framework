import { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  FlatList,
  Pressable,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";
import { mockAlerts, type Alert } from "../../lib/mock-data";

export default function SearchScreen() {
  const [query, setQuery] = useState("");

  const results: Alert[] = query.length > 0
    ? mockAlerts.filter(
        (a) =>
          a.title.toLowerCase().includes(query.toLowerCase()) ||
          a.description.toLowerCase().includes(query.toLowerCase()) ||
          (a.mitreTechnique?.toLowerCase().includes(query.toLowerCase()) ?? false)
      )
    : [];

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Search</Text>
      </View>

      {/* Search input */}
      <View style={styles.searchContainer}>
        <Ionicons name="search" size={18} color={colors.textMuted} />
        <TextInput
          style={styles.input}
          placeholder="Search alerts, MITRE techniques..."
          placeholderTextColor={colors.textLight}
          value={query}
          onChangeText={setQuery}
          autoCapitalize="none"
          autoCorrect={false}
        />
        {query.length > 0 && (
          <Pressable onPress={() => setQuery("")}>
            <Ionicons name="close-circle" size={18} color={colors.textMuted} />
          </Pressable>
        )}
      </View>

      {/* Quick filters */}
      <View style={styles.quickFilters}>
        {["T1068", "T1110", "Brute Force", "DNS", "Ransomware"].map((tag) => (
          <Pressable
            key={tag}
            style={styles.quickTag}
            onPress={() => setQuery(tag)}
          >
            <Text style={styles.quickTagText}>{tag}</Text>
          </Pressable>
        ))}
      </View>

      {/* Results */}
      {query.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="search" size={48} color={colors.bgSurface} />
          <Text style={styles.emptyTitle}>Search STRIX Database</Text>
          <Text style={styles.emptyDesc}>
            Search across alerts, MITRE techniques, and threat intelligence.
          </Text>
        </View>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>No results</Text>
              <Text style={styles.emptyDesc}>
                No matches found for "{query}"
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <Pressable style={styles.resultCard}>
              <View style={styles.resultHeader}>
                <View
                  style={[
                    styles.severityDot,
                    {
                      backgroundColor:
                        item.severity === "critical"
                          ? colors.critical
                          : item.severity === "warning"
                          ? colors.warning
                          : colors.primary,
                    },
                  ]}
                />
                <Text style={styles.resultTitle}>{item.title}</Text>
              </View>
              <Text style={styles.resultDesc} numberOfLines={2}>
                {item.description}
              </Text>
              {item.mitreTechnique && (
                <Text style={styles.resultMitre}>
                  {item.mitreTechnique} {"\u2022"} {item.mitreLabel}
                </Text>
              )}
            </Pressable>
          )}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  header: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  headerTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["4xl"],
    color: colors.textPrimary,
    letterSpacing: typography.tracking.tight,
  },
  searchContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    backgroundColor: colors.bgCard,
    borderRadius: radius.full,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
  },
  input: {
    flex: 1,
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  quickFilters: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  quickTag: {
    backgroundColor: colors.bgSurface,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.full,
  },
  quickTagText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.primary,
    letterSpacing: 0.5,
  },
  emptyState: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingTop: spacing["3xl"],
    gap: spacing.sm,
  },
  emptyTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xl,
    color: colors.textPrimary,
  },
  emptyDesc: {
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textMuted,
    textAlign: "center",
    maxWidth: 260,
  },
  list: {
    padding: spacing.lg,
    paddingBottom: spacing["3xl"],
  },
  resultCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadows.card,
  },
  resultHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  severityDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  resultTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.lg,
    color: colors.textPrimary,
    flex: 1,
  },
  resultDesc: {
    fontFamily: typography.family.body,
    fontSize: typography.size.md,
    color: colors.textBody,
    lineHeight: 20,
  },
  resultMitre: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.primary,
  },
});
