import { useEffect, useRef, useState } from "react";
import { Animated, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { LineChart } from "@/components/LineChart";
import { Reveal } from "@/components/Reveal";
import { Badge, Card, Divider, EmptyState, Metric, SectionHeader } from "@/components/ui";
import { usePolling } from "@/hooks/usePolling";
import { api } from "@/lib/api";
import { pct, usd } from "@/lib/format";
import { colors, fonts, radius, space } from "@/lib/theme";
import type { PredictionResponse } from "@/lib/types";

const WATCHLIST = ["NVDA", "AAPL", "MSFT", "AMD", "PLTR", "SMCI", "TSLA", "META"];

function signalTone(signal: PredictionResponse["signal"]) {
  if (signal === "BUY") return "positive" as const;
  if (signal === "SELL") return "negative" as const;
  return "neutral" as const;
}

function trendTone(trend: PredictionResponse["trend"]) {
  if (trend === "BULLISH") return "positive" as const;
  if (trend === "BEARISH") return "negative" as const;
  return "neutral" as const;
}

function delta(target: number, current: number): string {
  if (!current) return "—";
  return pct(((target - current) / current) * 100);
}

export default function PredictScreen() {
  const [ticker, setTicker] = useState(WATCHLIST[0]);
  const { data, error, loading, refreshing, refresh } = usePolling(
    () => api.prediction(ticker),
    60_000,
  );

  const scrollY = useRef(new Animated.Value(0)).current;
  const onScroll = Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], {
    useNativeDriver: Platform.OS !== "web",
  });

  useEffect(() => {
    void refresh();
  }, [ticker, refresh]);

  const prediction = data?.ticker === ticker ? data : null;
  const history = prediction?.chart_data.slice(-90).map((point) => point.price) ?? [];
  const confidencePct = prediction ? Math.round(prediction.confidence * 100) : 0;
  const signalColor =
    prediction?.signal === "BUY"
      ? colors.accent
      : prediction?.signal === "SELL"
        ? colors.danger
        : colors.muted;

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <Animated.ScrollView
        contentContainerStyle={styles.content}
        onScroll={onScroll}
        scrollEventThrottle={16}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.text} />
        }
      >
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>ENSEMBLE MODEL</Text>
            <Text style={styles.title}>Prediction</Text>
          </View>
          {prediction ? (
            <Badge label={prediction.signal} tone={signalTone(prediction.signal)} />
          ) : null}
        </View>

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chips}
        >
          {WATCHLIST.map((symbol) => {
            const active = symbol === ticker;
            return (
              <Pressable
                key={symbol}
                onPress={() => setTicker(symbol)}
                style={({ pressed }) => [
                  styles.chip,
                  active && styles.chipActive,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{symbol}</Text>
              </Pressable>
            );
          })}
        </ScrollView>

        {error ? (
          <Reveal index={0}>
            <Card style={styles.errorCard}>
              <SectionHeader title="Prediction failed" right={<Badge label="error" tone="negative" />} />
              <Text style={styles.errorText}>{error.message}</Text>
            </Card>
          </Reveal>
        ) : null}

        {loading && !prediction ? (
          <Reveal index={1}>
            <Card>
              <EmptyState text={`Running ensemble for ${ticker}… first call can take ~20s.`} />
            </Card>
          </Reveal>
        ) : null}

        {prediction ? (
          <>
            <Reveal scrollY={scrollY} index={0}>
              <Card>
                <View style={styles.priceRow}>
                  <View>
                    <Text style={styles.company}>{prediction.name || prediction.ticker}</Text>
                    <Text style={styles.price}>{usd(prediction.current_price)}</Text>
                    <Text style={styles.sector}>{prediction.sector}</Text>
                  </View>
                  <View style={styles.priceRight}>
                    <Badge label={prediction.trend} tone={trendTone(prediction.trend)} />
                    <Text style={styles.forecast}>{usd(prediction.forecast_price)}</Text>
                    <Text style={styles.forecastLabel}>7d forecast</Text>
                  </View>
                </View>

                <View style={styles.confidenceBlock}>
                  <View style={styles.confidenceRow}>
                    <Text style={styles.confidenceLabel}>Confidence</Text>
                    <Text style={[styles.confidenceValue, { color: signalColor }]}>
                      {confidencePct}%
                    </Text>
                  </View>
                  <View style={styles.track}>
                    <View
                      style={[
                        styles.fill,
                        { width: `${Math.min(confidencePct, 100)}%`, backgroundColor: signalColor },
                      ]}
                    />
                  </View>
                </View>
              </Card>
            </Reveal>

            <Reveal scrollY={scrollY} index={1}>
              <Card>
                <SectionHeader title="Price history" right={<Badge label="90 sessions" />} />
                {history.length > 1 ? (
                  <LineChart
                    values={history}
                    height={170}
                    color={prediction.trend === "BEARISH" ? colors.danger : colors.accent}
                    formatAxis={(value) => `$${value.toFixed(0)}`}
                  />
                ) : (
                  <EmptyState text="No chart data returned." />
                )}
              </Card>
            </Reveal>

            <Reveal scrollY={scrollY} index={2}>
              <Card>
                <SectionHeader title="Targets" />
                <View style={styles.targetRow}>
                  <Metric
                    label="7 days"
                    value={usd(prediction.price_target_7d)}
                    sub={delta(prediction.price_target_7d, prediction.current_price)}
                  />
                  <Metric
                    label="14 days"
                    value={usd(prediction.price_target_14d)}
                    sub={delta(prediction.price_target_14d, prediction.current_price)}
                  />
                  <Metric
                    label="30 days"
                    value={usd(prediction.price_target_30d)}
                    sub={delta(prediction.price_target_30d, prediction.current_price)}
                  />
                </View>
              </Card>
            </Reveal>

            <Reveal scrollY={scrollY} index={3}>
              <Card>
                <SectionHeader title="Indicators" />
                <View style={styles.targetRow}>
                  <Metric
                    label="RSI 14"
                    value={prediction.rsi === null ? "—" : prediction.rsi.toFixed(1)}
                  />
                  <Metric
                    label="MACD"
                    value={prediction.macd === null ? "—" : prediction.macd.toFixed(2)}
                  />
                  <Metric
                    label="Sentiment"
                    value={prediction.sentiment_score.toFixed(2)}
                    tone={
                      prediction.sentiment_score > 0
                        ? "positive"
                        : prediction.sentiment_score < 0
                          ? "negative"
                          : "neutral"
                    }
                  />
                </View>
                <Divider />
                <View style={styles.targetRow}>
                  <Metric
                    label="SMA 20"
                    value={prediction.sma_20 === null ? "—" : usd(prediction.sma_20)}
                  />
                  <Metric
                    label="SMA 50"
                    value={prediction.sma_50 === null ? "—" : usd(prediction.sma_50)}
                  />
                  <Metric
                    label="Bollinger"
                    value={
                      prediction.bollinger_upper === null
                        ? "—"
                        : `${usd(prediction.bollinger_lower ?? 0, 0)}–${usd(prediction.bollinger_upper, 0)}`
                    }
                  />
                </View>
              </Card>
            </Reveal>
          </>
        ) : null}
      </Animated.ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  content: { padding: 18, gap: space.md, paddingBottom: 44 },
  header: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    paddingTop: 4,
    marginBottom: 2,
  },
  eyebrow: { color: colors.muted, fontSize: 9.5, letterSpacing: 2.6, fontWeight: "700" },
  title: {
    fontFamily: fonts.display,
    fontSize: 32,
    fontWeight: "400",
    letterSpacing: -0.7,
    color: colors.text,
  },
  chips: { gap: 8, paddingRight: 18 },
  chip: {
    paddingHorizontal: 15,
    paddingVertical: 7,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.panel,
  },
  chipActive: { backgroundColor: colors.text, borderColor: colors.text },
  pressed: { opacity: 0.7 },
  chipText: { color: colors.muted, fontSize: 12, fontWeight: "600" },
  chipTextActive: { color: colors.panel },
  errorCard: { borderColor: colors.danger },
  errorText: { color: colors.danger, fontSize: 12 },
  priceRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  company: { color: colors.muted, fontSize: 13, fontWeight: "600" },
  price: {
    color: colors.text,
    fontSize: 32,
    fontWeight: "600",
    letterSpacing: -0.8,
    marginTop: 3,
    fontVariant: ["tabular-nums"],
  },
  sector: { color: colors.faint, fontSize: 11, marginTop: 3 },
  priceRight: { alignItems: "flex-end", gap: 4 },
  forecast: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "600",
    fontVariant: ["tabular-nums"],
  },
  forecastLabel: { color: colors.faint, fontSize: 10, letterSpacing: 0.6 },
  confidenceBlock: { gap: 7, marginTop: space.xs },
  confidenceRow: { flexDirection: "row", justifyContent: "space-between" },
  confidenceLabel: {
    color: colors.faint,
    fontSize: 9.5,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    fontWeight: "600",
  },
  confidenceValue: { fontSize: 12, fontWeight: "700" },
  track: { height: 4, borderRadius: 2, backgroundColor: colors.track, overflow: "hidden" },
  fill: { height: 4, borderRadius: 2 },
  targetRow: { flexDirection: "row", flexWrap: "wrap", columnGap: space.md, rowGap: space.xs },
});
