import { useEffect, useRef } from "react";
import { Animated, StyleSheet, View, type ViewStyle } from "react-native";
import { colors, radius } from "../lib/theme";

/**
 * Pulsing placeholder rectangle. Cheap — a single Animated.Value +
 * `useNativeDriver: true` so it runs on the UI thread without JS hops
 * even while we're waiting on slow queries.
 */

interface Props {
  width?: number | `${number}%`;
  height?: number;
  borderRadius?: number;
  style?: ViewStyle;
}

export function Skeleton({
  width = "100%",
  height = 16,
  borderRadius = radius.sm,
  style,
}: Props) {
  const anim = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(anim, {
          toValue: 1,
          duration: 700,
          useNativeDriver: true,
        }),
        Animated.timing(anim, {
          toValue: 0.4,
          duration: 700,
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [anim]);

  return (
    <Animated.View
      style={[
        styles.base,
        { width, height, borderRadius, opacity: anim },
        style,
      ]}
    />
  );
}

export function SkeletonBlock({
  lines = 2,
  lineHeight = 14,
  gap = 8,
}: {
  lines?: number;
  lineHeight?: number;
  gap?: number;
}) {
  return (
    <View style={{ gap }}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height={lineHeight}
          width={i === lines - 1 ? "70%" : "100%"}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    backgroundColor: colors.bgSurface,
  },
});
