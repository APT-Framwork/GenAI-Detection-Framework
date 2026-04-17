import { View, StyleSheet } from "react-native";
import Svg, { Polyline, Defs, LinearGradient, Stop, Rect } from "react-native-svg";
import { colors, radius } from "../lib/theme";
import type { ChartPoint } from "../lib/mock-data";

interface Props {
  data: ChartPoint[];
  width?: number;
  height?: number;
  color?: string;
}

export function MiniChart({
  data,
  width = 342,
  height = 192,
  color = colors.primary,
}: Props) {
  if (data.length === 0) return null;

  const maxVal = Math.max(...data.map((d) => d.value));
  const minVal = Math.min(...data.map((d) => d.value));
  const range = maxVal - minVal || 1;
  const padding = 16;
  const chartW = width - padding * 2;
  const chartH = height - padding * 2;

  const points = data
    .map((d, i) => {
      const x = padding + (i / (data.length - 1)) * chartW;
      const y = padding + chartH - ((d.value - minVal) / range) * chartH;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <View style={[styles.container, { width, height }]}>
      <Svg width={width} height={height}>
        <Defs>
          <LinearGradient id="gridColor" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={colors.textMuted} stopOpacity="0.1" />
            <Stop offset="1" stopColor={colors.textMuted} stopOpacity="0" />
          </LinearGradient>
        </Defs>
        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map((frac) => (
          <Rect
            key={frac}
            x={padding}
            y={padding + chartH * frac}
            width={chartW}
            height={0.5}
            fill={colors.textMuted}
            opacity={0.15}
          />
        ))}
        <Polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <Polyline
          points={points}
          fill="none"
          stroke={colors.bgAccent}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.4}
          translateY={4}
        />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.bgSurface,
    borderRadius: radius.lg,
    overflow: "hidden",
  },
});
