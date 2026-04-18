import { useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, typography, spacing, radius } from "../../lib/theme";
import { AlertCard } from "../../components/AlertCard";
import {
  useAcknowledgeAlert,
  useAlertsInfinite,
  useUnacknowledgedCount,
  type AlertSeverityFilter,
} from "../../lib/api/hooks";

const FILTERS: { key: AlertSeverityFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "critical", label: "Critical" },
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
];

export default function AlertsScreen() {
  const [filter, setFilter] = useState<AlertSeverityFilter>("all");

  const listQ = useAlertsInfinite({ severity: filter, limit: 30 });
  const unackQ = useUnacknowledgedCount();
  const ackMut = useAcknowledgeAlert();

  const alerts = useMemo(
    () => (listQ.data?.pages ?? []).flatMap((p) => p.items),
    [listQ.data],
  );

  const onEndReached = () => {
    if (listQ.hasNextPage && !listQ.isFetchingNextPage) {
      void listQ.fetchNextPage();
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
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

      {/* Page title */}
      <View style={styles.titleSection}>
        <Text style={styles.subtitle}>LIVE SECURITY FEED</Text>
        <Text style={styles.title}>STRIX Notifications</Text>
      </View>

      {/* Filters */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filterScroll}
        contentContainerStyle={styles.filterRow}
      >
        {FILTERS.map((f) => {
          const active = filter === f.key;
          const suffix =
            f.key === "all" && unackQ.data
              ? ` (${unackQ.data.count} unack)`
              : "";
          return (
            <Pressable
              key={f.key}
              style={[styles.filterChip, active && styles.filterChipActive]}
              onPress={() => setFilter(f.key)}
            >
              <Text
                style={[
                  styles.filterText,
                  active && styles.filterTextActive,
                ]}
              >
                {f.label}
                {suffix}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {/* List */}
      {listQ.isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : listQ.isError ? (
        <View style={styles.center}>
          <Text style={styles.emptyTitle}>Couldn't load alerts</Text>
          <Text style={styles.emptyDesc}>
            {(listQ.error as Error)?.message ?? "Check backend connection."}
          </Text>
          <Pressable
            style={styles.retryBtn}
            onPress={() => void listQ.refetch()}
          >
            <Text style={styles.retryText}>RETRY</Text>
          </Pressable>
        </View>
      ) : alerts.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyTitle}>No alerts</Text>
          <Text style={styles.emptyDesc}>
            {filter === "all"
              ? "The backend has no alerts in this window."
              : `No ${filter} alerts in the current window.`}
          </Text>
        </View>
      ) : (
        <FlatList
          data={alerts}
          keyExtractor={(item) => `${item.alertId}:${item.occurredAt}`}
          renderItem={({ item }) => (
            <AlertCard
              alert={item}
              onAcknowledge={(args) => ackMut.mutate(args)}
              acknowledging={
                ackMut.isPending &&
                ackMut.variables?.alertId === item.alertId
              }
            />
          )}
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
          ItemSeparatorComponent={() => (
            <View style={{ height: spacing.md }} />
          )}
          onEndReached={onEndReached}
          onEndReachedThreshold={0.4}
          ListFooterComponent={
            listQ.isFetchingNextPage ? (
              <View style={styles.footerLoader}>
                <ActivityIndicator color={colors.primary} />
              </View>
            ) : null
          }
          refreshControl={
            <RefreshControl
              refreshing={listQ.isRefetching && !listQ.isFetchingNextPage}
              onRefresh={() => void listQ.refetch()}
              tintColor={colors.primary}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
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
    width: 40,
    height: 40,
    borderRadius: radius.full,
    backgroundColor: colors.bgAccentSoft,
  },
  titleSection: {
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
  },
  subtitle: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.textMuted,
    letterSpacing: typography.tracking.widest,
  },
  title: {
    fontFamily: typography.family.heading,
    fontSize: typography.size["5xl"],
    color: colors.textPrimary,
    letterSpacing: typography.tracking.tight,
  },
  filterScroll: { maxHeight: 48, marginTop: spacing.md },
  filterRow: {
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
    alignItems: "center",
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.full,
    backgroundColor: colors.bgSurface,
  },
  filterChipActive: { backgroundColor: colors.primary },
  filterText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.xs,
    color: colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  filterTextActive: { color: colors.primaryLight },
  list: {
    padding: spacing.lg,
    paddingBottom: spacing["2xl"],
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
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
  },
  retryBtn: {
    marginTop: spacing.md,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
  },
  retryText: {
    fontFamily: typography.family.heading,
    fontSize: typography.size.sm,
    color: colors.white,
    letterSpacing: 1,
  },
  footerLoader: {
    paddingVertical: spacing.lg,
  },
});
