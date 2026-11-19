import { useCallback, useRef } from "react";
import { Animated, Platform, RefreshControl, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { AnimatedNumber } from "@/components/AnimatedNumber";
import { LineChart } from "@/components/LineChart";
import { Reveal } from "@/components/Reveal";
import { Badge, Card, Divider, EmptyState, Metric, SectionHeader } from "@/components/ui";
import { usePolling } from "@/hooks/usePolling";
import { API_BASE, ApiError, api } from "@/lib/api";
import { pct, signedUsd, timeAgo, usd } from "@/lib/format";
import { colors, fonts, space } from "@/lib/theme";
import type { LedgerRecord } from "@/lib/types";

function reasonText(record: LedgerRecord): string {
  const codes = Array.isArray(record.reason_codes) ? record.reason_codes : [record.reason_codes];
  const joined = codes.filter(Boolean).join(", ");
  return joined || "—";
}

function toneOf(value: number): "positive" | "negative" | "neutral" {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

export default function OpsScreen() {
  const insets = useSafeAreaInsets();
  const summary = usePolling(api.summary, 15_000);
  const curve = usePolling(() => api.equityCurve(240), 60_000);
  const rejected = usePolling(() => api.rejected(10), 60_000);

  const scrollY = useRef(new Animated.Value(0)).current;
  const onScroll = Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], {
    useNativeDriver: Platform.OS !== "web",
  });
  const compactOpacity = scrollY.interpolate({
    inputRange: [70, 150],
    outputRange: [0, 1],
    extrapolate: "clamp",
  });
  const heroStyle = {
    opacity: scrollY.interpolate({
      inputRange: [0, 140],
      outputRange: [1, 0],
      extrapolate: "clamp",
    }),
    transform: [
      {
        translateY: scrollY.interpolate({
          inputRange: [0, 180],
          outputRange: [0, -16],
          extrapolate: "clamp",
        }),
      },
    ],
  };

  const refresh = useCallback(() => {
    void summary.refresh();
    void curve.refresh();
    void rejected.refresh();
  }, [summary.refresh, curve.refresh, rejected.refresh]);

  const s = summary.data;
  const points = curve.data?.points ?? [];
  const equityValues = points.map((p) => p.equity);
  const killActive = s?.summary.kill_switch_active ?? false;
  const refreshing = summary.refreshing || curve.refreshing || rejected.refreshing;

  return (
    <View style={styles.root}>
      <Animated.View
        pointerEvents="none"
        style={[styles.compactBar, { opacity: compactOpacity, paddingTop: insets.top + 10 }]}
      >
        <Text style={styles.compactBrand}>StockSense</Text>
        <View style={styles.compactRight}>
          {s ? <Text style={styles.compactMeta}>Ops · {timeAgo(s.generated_at)}</Text> : null}
          <Badge label="SIMULATE" tone="info" />
        </View>
      </Animated.View>

      <SafeAreaView style={styles.safe} edges={["top"]}>
        <Animated.ScrollView
          contentContainerStyle={styles.content}
          onScroll={onScroll}
          scrollEventThrottle={16}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={refresh}
              tintColor={colors.text}
            />
          }
        >
          <Animated.View style={[styles.hero, heroStyle]}>
            <Text style={styles.eyebrow}>STOCKSENSE</Text>
            <Text style={styles.title}>Ops Console</Text>
            <View style={styles.statusRow}>
              <View
                style={[
                  styles.dot,
                  { backgroundColor: s?.account.verified ? colors.accent : colors.danger },
                ]}
              />
              <Text style={styles.statusText}>
                {s
                  ? `${s.account.source || "moomoo"} · acc ${s.account.account_id} · ${s.account.verified ? "verified" : "unverified"}`
                  : "Connecting…"}
              </Text>
              {s ? <Text style={styles.statusMeta}>{timeAgo(s.generated_at)}</Text> : null}
            </View>
            <Text style={styles.apiBase}>{API_BASE}</Text>
          </Animated.View>

          {summary.error ? (
            <Reveal index={0}>
              <Card style={styles.errorCard}>
                <SectionHeader
                  title="Backend unreachable"
                  right={<Badge label="offline" tone="negative" />}
                />
                <Text style={styles.errorText}>
                  {(summary.error as ApiError).code ?? "ERROR"}: {summary.error.message}
                </Text>
                <Text style={styles.errorHint}>
                  Start the FastAPI backend on :8000 and confirm CORS allows{" "}
                  {API_BASE.replace("8000", "8081")}.
                </Text>
              </Card>
            </Reveal>
          ) : null}

          {killActive ? (
            <Reveal index={0}>
              <View style={styles.killBanner}>
                <Text style={styles.killTitle}>KILL SWITCH ACTIVE</Text>
                <Text style={styles.killText}>
                  {s?.kill_switch.reason || "Trading halted by operator"} — orders are blocked.
                </Text>
              </View>
            </Reveal>
          ) : null}

          <Reveal scrollY={scrollY} index={0}>
            <Card>
              <SectionHeader
                title="Account"
                right={
                  <Badge
                    label={s?.demo ? "demo" : "live paper"}
                    tone={s?.demo ? "warning" : "positive"}
                  />
                }
              />
              <View style={styles.metricGrid}>
                <Metric
                  label="Equity"
                  value={s ? <AnimatedNumber value={s.summary.equity} format={(v) => usd(v)} /> : "…"}
                  sub={s ? `${s.summary.position_count} positions` : undefined}
                />
                <Metric
                  label="Cash"
                  value={s ? <AnimatedNumber value={s.summary.cash} format={(v) => usd(v)} /> : "…"}
                  sub={s ? `${s.summary.gross_exposure_pct.toFixed(1)}% exposure` : undefined}
                />
                <Metric
                  label="Day P&L"
                  value={
                    s ? <AnimatedNumber value={s.summary.day_pnl} format={(v) => signedUsd(v)} /> : "…"
                  }
                  sub={s ? pct(s.summary.day_pnl_pct) : undefined}
                  tone={s ? toneOf(s.summary.day_pnl) : "neutral"}
                />
                <Metric
                  label="Total P&L"
                  value={
                    s ? (
                      <AnimatedNumber value={s.summary.total_pnl} format={(v) => signedUsd(v)} />
                    ) : (
                      "…"
                    )
                  }
                  sub={
                    s
                      ? `${pct(s.summary.total_return_pct)} vs ${usd(s.summary.baseline_equity, 0)}`
                      : undefined
                  }
                  tone={s ? toneOf(s.summary.total_pnl) : "neutral"}
                />
                <Metric
                  label="Rejected"
                  value={s ? String(s.ledger.rejected) : "…"}
                  sub={s ? `${s.ledger.total_events} ledger events` : undefined}
                  tone={s && s.ledger.rejected > 0 ? "warning" : "neutral"}
                />
                <Metric
                  label="Filled"
                  value={s ? String(s.ledger.filled) : "…"}
                  sub={s ? `${s.ledger.approved} approved` : undefined}
                  tone="positive"
                />
              </View>
            </Card>
          </Reveal>

          <Reveal scrollY={scrollY} index={1}>
            <Card>
              <SectionHeader
                title="Equity curve"
                right={<Badge label={curve.data ? `${curve.data.count} pts` : "loading"} />}
              />
              {equityValues.length > 1 ? (
                <LineChart
                  values={equityValues}
                  baseline={s?.summary.baseline_equity ?? null}
                  height={160}
                />
              ) : (
                <EmptyState text={curve.error ? curve.error.message : "Collecting snapshots…"} />
              )}
            </Card>
          </Reveal>

          <Reveal scrollY={scrollY} index={2}>
            <Card>
              <SectionHeader
                title="Positions"
                right={s ? <Badge label={String(s.positions.length)} /> : null}
              />
              {s && s.positions.length > 0 ? (
                s.positions.map((position, index) => (
                  <View key={position.ticker}>
                    {index > 0 ? <Divider /> : null}
                    <View style={styles.row}>
                      <View style={styles.rowLeft}>
                        <Text style={styles.rowTitle}>{position.ticker}</Text>
                        <Text style={styles.rowSub}>
                          {position.quantity} sh · {usd(position.market_value)}
                        </Text>
                      </View>
                      <Text style={styles.rowValue}>
                        {(position.allocation_pct ?? 0).toFixed(2)}%
                      </Text>
                    </View>
                  </View>
                ))
              ) : (
                <EmptyState text={s ? "No open positions." : "Loading…"} />
              )}
            </Card>
          </Reveal>

          <Reveal scrollY={scrollY} index={3}>
            <Card>
              <SectionHeader
                title="Recent rejections"
                right={
                  <Badge
                    label={rejected.data ? String(rejected.data.count) : "0"}
                    tone="warning"
                  />
                }
              />
              {rejected.data && rejected.data.rejections.length > 0 ? (
                rejected.data.rejections.map((record, index) => (
                  <View key={`${record.decision_id}-${index}`}>
                    {index > 0 ? <Divider /> : null}
                    <View style={styles.row}>
                      <View style={styles.rowLeft}>
                        <Text style={styles.rowTitle}>
                          {record.side} {record.quantity} {record.ticker}
                        </Text>
                        <Text style={styles.rowSub}>{reasonText(record)}</Text>
                      </View>
                      <Text style={styles.rowMeta}>{timeAgo(record.event_time)}</Text>
                    </View>
                  </View>
                ))
              ) : (
                <EmptyState text="No rejected orders. Risk gate is clean." />
              )}
            </Card>
          </Reveal>

          <Text style={styles.footer}>
            Paper trading only · SIMULATE environment
            {s ? ` · ${s.summary.snapshot_storage}` : ""}
          </Text>
        </Animated.ScrollView>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  safe: { flex: 1 },
  compactBar: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 18,
    paddingBottom: 10,
    backgroundColor: "rgba(246, 244, 239, 0.98)",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  compactBrand: {
    fontFamily: fonts.display,
    fontSize: 17,
    color: colors.text,
    letterSpacing: -0.2,
  },
  compactRight: { flexDirection: "row", alignItems: "center", gap: 8 },
  compactMeta: { color: colors.faint, fontSize: 10.5 },
  content: { padding: 18, gap: space.md, paddingBottom: 44 },
  hero: { gap: 3, paddingTop: 4 },
  eyebrow: {
    color: colors.muted,
    fontSize: 9.5,
    letterSpacing: 2.6,
    fontWeight: "700",
  },
  title: {
    fontFamily: fonts.display,
    fontSize: 32,
    fontWeight: "400",
    letterSpacing: -0.7,
    color: colors.text,
  },
  statusRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { color: colors.muted, fontSize: 12, flexShrink: 1 },
  statusMeta: { color: colors.faint, fontSize: 11, marginLeft: "auto" },
  apiBase: { color: colors.faint, fontSize: 10, marginTop: 1 },
  errorCard: { borderColor: colors.danger },
  errorText: { color: colors.danger, fontSize: 12 },
  errorHint: { color: colors.muted, fontSize: 11 },
  killBanner: {
    backgroundColor: colors.dangerSoft,
    borderColor: colors.danger,
    borderWidth: 1,
    borderRadius: 16,
    padding: space.sm + 2,
    gap: 2,
  },
  killTitle: { color: colors.danger, fontSize: 11, fontWeight: "800", letterSpacing: 1.4 },
  killText: { color: colors.danger, fontSize: 12 },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", columnGap: space.md },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 7,
  },
  rowLeft: { flex: 1, gap: 2 },
  rowTitle: { color: colors.text, fontSize: 14, fontWeight: "600" },
  rowSub: { color: colors.faint, fontSize: 11 },
  rowValue: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "500",
    fontVariant: ["tabular-nums"],
  },
  rowMeta: { color: colors.faint, fontSize: 11 },
  footer: {
    color: colors.faint,
    fontSize: 10,
    textAlign: "center",
    marginTop: space.xs,
  },
});
