import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import { colors, typography, spacing, radius, shadows } from "../../lib/theme";
import { useColors } from "../../lib/theme-hook";
import {
  useFileScan,
  useIocSearch,
  type FileScanResponse,
  type IocItem,
} from "../../lib/api/hooks";
import { useJobResult } from "../../lib/api/sse";

const QUICK_TAGS = ["admin@", "8.8.8.8", "example.com", "hash:"];

function statusLabel(status: string | undefined): string {
  if (!status) return "—";
  return status.toUpperCase();
}

function reputationColor(
  rep: IocItem["reputation"],
  c: ReturnType<typeof useColors>,
): string {
  switch (rep) {
    case "malicious":
      return c.critical;
    case "suspicious":
      return c.warning;
    case "clean":
      return c.success;
    default:
      return c.textMuted;
  }
}

export default function SearchScreen() {
  const c = useColors();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [scan, setScan] = useState<FileScanResponse | null>(null);
  const fileScan = useFileScan();

  // 350 ms debounce — avoids thrashing HIBP / VirusTotal as the user types.
  useEffect(() => {
    const id = setTimeout(() => setDebounced(query), 350);
    return () => clearTimeout(id);
  }, [query]);

  const searchQ = useIocSearch(debounced);
  const results = searchQ.data?.items ?? [];

  // Subscribe to the job SSE once the upload returns a scanId.
  const job = useJobResult(scan?.scanId ?? null);
  const jobLatest = job.events[0];

  async function onPickFile() {
    const result = await DocumentPicker.getDocumentAsync({
      copyToCacheDirectory: true,
      multiple: false,
    });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    try {
      const resp = await fileScan.mutateAsync({
        uri: asset.uri,
        name: asset.name,
        mime: asset.mimeType ?? undefined,
      });
      setScan(resp);
    } catch {
      // Error surfaces via fileScan.isError in the UI below.
    }
  }

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.bg }]}
      edges={["top"]}
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={[styles.headerTitle, { color: c.textPrimary }]}>
          Threat Intel
        </Text>
      </View>

      {/* Search input */}
      <View
        style={[
          styles.searchContainer,
          { backgroundColor: c.bgCard, borderColor: c.border },
        ]}
      >
        <Ionicons name="search" size={18} color={c.textMuted} />
        <TextInput
          style={[styles.input, { color: c.textPrimary }]}
          placeholder="Search IOC: email, IP, domain, hash…"
          placeholderTextColor={c.textLight}
          value={query}
          onChangeText={setQuery}
          autoCapitalize="none"
          autoCorrect={false}
        />
        {query.length > 0 ? (
          <Pressable onPress={() => setQuery("")}>
            <Ionicons name="close-circle" size={18} color={c.textMuted} />
          </Pressable>
        ) : null}
      </View>

      {/* Quick tags */}
      <View style={styles.quickFilters}>
        {QUICK_TAGS.map((tag) => (
          <Pressable
            key={tag}
            style={[styles.quickTag, { backgroundColor: c.bgSurface }]}
            onPress={() => setQuery(tag)}
          >
            <Text style={[styles.quickTagText, { color: c.primary }]}>
              {tag}
            </Text>
          </Pressable>
        ))}
      </View>

      {/* File scan */}
      <Pressable
        style={[styles.scanCard, { backgroundColor: c.bgCard }]}
        disabled={fileScan.isPending}
        onPress={onPickFile}
      >
        <View style={[styles.scanIcon, { backgroundColor: c.bgAccentSoft }]}>
          {fileScan.isPending ? (
            <ActivityIndicator color={c.primary} />
          ) : (
            <Ionicons name="cloud-upload-outline" size={18} color={c.primary} />
          )}
        </View>
        <View style={styles.scanContent}>
          <Text style={[styles.scanTitle, { color: c.textPrimary }]}>
            {fileScan.isPending
              ? "Uploading…"
              : scan
              ? scan.filename
              : "Scan a file"}
          </Text>
          <Text style={[styles.scanDesc, { color: c.textMuted }]} numberOfLines={1}>
            {fileScan.isError
              ? "Upload failed — tap to retry"
              : scan
              ? `${statusLabel(jobLatest?.status ?? scan.status)} · ${scan.sha256.slice(0, 12)}…`
              : "VirusTotal via async job · ≤10 MB"}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={c.textLight} />
      </Pressable>

      {/* Results */}
      {query.trim().length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="search" size={48} color={c.bgSurface} />
          <Text style={[styles.emptyTitle, { color: c.textPrimary }]}>
            Threat Intelligence Search
          </Text>
          <Text style={[styles.emptyDesc, { color: c.textMuted }]}>
            Cached IOC lookups + on-demand HIBP and VirusTotal enrichment.
          </Text>
        </View>
      ) : searchQ.isLoading || (searchQ.isFetching && query !== debounced) ? (
        <View style={styles.emptyState}>
          <ActivityIndicator color={c.primary} />
        </View>
      ) : searchQ.isError ? (
        <View style={styles.emptyState}>
          <Text style={[styles.emptyTitle, { color: c.textPrimary }]}>
            Lookup failed
          </Text>
          <Text style={[styles.emptyDesc, { color: c.textMuted }]}>
            {(searchQ.error as Error)?.message ?? "Check backend connection."}
          </Text>
        </View>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(item, idx) => `${item.indicator}:${idx}`}
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Text style={[styles.emptyTitle, { color: c.textPrimary }]}>
                No results
              </Text>
              <Text style={[styles.emptyDesc, { color: c.textMuted }]}>
                No cached IOC matches "{debounced}".
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <Pressable
              style={[styles.resultCard, { backgroundColor: c.bgCard }]}
            >
              <View style={styles.resultHeader}>
                <View
                  style={[
                    styles.severityDot,
                    { backgroundColor: reputationColor(item.reputation, c) },
                  ]}
                />
                <Text
                  style={[styles.resultTitle, { color: c.textPrimary }]}
                  numberOfLines={1}
                >
                  {item.indicator}
                </Text>
                <Text
                  style={[
                    styles.typeBadge,
                    { color: c.primary, backgroundColor: c.bgSurface },
                  ]}
                >
                  {item.type.toUpperCase()}
                </Text>
              </View>
              <View style={styles.resultMetaRow}>
                <Text
                  style={[
                    styles.resultReputation,
                    { color: reputationColor(item.reputation, c) },
                  ]}
                >
                  {item.reputation.toUpperCase()}
                </Text>
                <Text style={[styles.resultSource, { color: c.textMuted }]}>
                  {item.source}
                  {item.stale ? " · STALE" : ""}
                </Text>
              </View>
              {item.breachCount !== null && item.breachCount > 0 ? (
                <Text style={[styles.breachText, { color: c.critical }]}>
                  {item.breachCount} breach{item.breachCount === 1 ? "" : "es"}
                </Text>
              ) : null}
            </Pressable>
          )}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
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
  scanCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.md,
    ...shadows.card,
  },
  scanIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.bgAccent,
    alignItems: "center",
    justifyContent: "center",
  },
  scanContent: { flex: 1, gap: 2 },
  scanTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.md,
    color: colors.textPrimary,
  },
  scanDesc: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.textMuted,
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
  list: { padding: spacing.lg, paddingBottom: spacing["3xl"] },
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
  severityDot: { width: 8, height: 8, borderRadius: 4 },
  resultTitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.lg,
    color: colors.textPrimary,
    flex: 1,
  },
  typeBadge: {
    fontFamily: typography.family.heading,
    fontSize: 9,
    color: colors.primary,
    backgroundColor: colors.bgSurface,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    letterSpacing: 0.8,
  },
  resultMetaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  resultReputation: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    letterSpacing: 0.8,
  },
  resultSource: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    letterSpacing: 0.5,
  },
  breachText: {
    fontFamily: typography.family.body,
    fontSize: typography.size.sm,
    color: colors.critical,
  },
});
