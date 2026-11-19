import { useState } from "react";
import { StyleSheet, View, type LayoutChangeEvent } from "react-native";
import Svg, {
  Circle,
  Defs,
  Line,
  LinearGradient,
  Path,
  Stop,
  Text as SvgText,
} from "react-native-svg";

import { colors } from "@/lib/theme";

interface Props {
  values: number[];
  height?: number;
  color?: string;
  baseline?: number | null;
  formatAxis?: (value: number) => string;
}

export function LineChart({
  values,
  height = 150,
  color = colors.chart,
  baseline = null,
  formatAxis,
}: Props) {
  const [width, setWidth] = useState(0);
  const onLayout = (event: LayoutChangeEvent) => setWidth(event.nativeEvent.layout.width);

  const points = values.filter((v) => Number.isFinite(v));
  const hasData = points.length > 0;
  const padX = 10;
  const padY = 18;
  const plotW = Math.max(width - padX * 2, 0);
  const plotH = height - padY * 2;

  let body = null;
  if (hasData && width > 0 && plotH > 0) {
    const candidates = baseline === null ? points : [...points, baseline];
    const min = Math.min(...candidates);
    const max = Math.max(...candidates);
    const range = max - min || Math.max(Math.abs(max) * 0.001, 1);

    const toX = (index: number) =>
      padX + (points.length === 1 ? plotW / 2 : (index / (points.length - 1)) * plotW);
    const toY = (value: number) => padY + (1 - (value - min) / range) * plotH;

    const line = points
      .map((value, index) => `${index === 0 ? "M" : "L"}${toX(index).toFixed(1)},${toY(value).toFixed(1)}`)
      .join(" ");
    const area = `${line} L${toX(points.length - 1).toFixed(1)},${height - padY} L${toX(0).toFixed(1)},${height - padY} Z`;
    const lastValue = points[points.length - 1];
    const axisLabel = formatAxis ?? ((value: number) => `$${(value / 1000).toFixed(1)}k`);

    body = (
      <>
        <Defs>
          <LinearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color} stopOpacity="0.16" />
            <Stop offset="1" stopColor={color} stopOpacity="0.01" />
          </LinearGradient>
        </Defs>
        {baseline !== null ? (
          <Line
            x1={padX}
            y1={toY(baseline)}
            x2={padX + plotW}
            y2={toY(baseline)}
            stroke={colors.borderStrong}
            strokeWidth={1}
            strokeDasharray="4 4"
            opacity={0.6}
          />
        ) : null}
        <Path d={area} fill="url(#fill)" />
        <Path d={line} stroke={color} strokeWidth={1.8} fill="none" strokeLinejoin="round" />
        <Circle cx={toX(points.length - 1)} cy={toY(lastValue)} r={3} fill={color} />
        <SvgText x={padX} y={12} fill={colors.faint} fontSize={9}>
          {axisLabel(max)}
        </SvgText>
        <SvgText x={padX} y={height - 4} fill={colors.faint} fontSize={9}>
          {axisLabel(min)}
        </SvgText>
      </>
    );
  }

  return (
    <View style={[styles.container, { height }]} onLayout={onLayout}>
      {width > 0 ? (
        <Svg width={width} height={height}>
          {body}
        </Svg>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: "100%",
  },
});
