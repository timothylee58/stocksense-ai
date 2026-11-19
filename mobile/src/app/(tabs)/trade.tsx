import { useCallback, useRef, useState } from "react";
import {
  Animated,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Reveal } from "@/components/Reveal";
import { Badge, Card, Divider, EmptyState, SectionHeader } from "@/components/ui";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, api } from "@/lib/api";
import { clockTime, usd } from "@/lib/format";
import { colors, fonts, radius, space } from "@/lib/theme";
import type { OrderResponse, Side } from "@/lib/types";

function newKey(): string {
  return `mobile-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function executionTone(status: string) {
  if (status === "submitted" || status === "filled") return "positive" as const;
  if (status === "dry_run") return "info" as const;
  if (status === "duplicate_blocked") return "warning" as const;
  return "negative" as const;
}

export default function TradeScreen() {
  const [ticker, setTicker] = useState("NVDA");
  const [side, setSide] = useState<Side>("BUY");
  const [quantity, setQuantity] = useState("1");
  const [price, setPrice] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<OrderResponse | null>(null);
  const [submitError, setSubmitError] = useState("");
  const [markLoading, setMarkLoading] = useState(false);

  const scrollY = useRef(new Animated.Value(0)).current;
  const onScroll = Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], {
    useNativeDriver: Platform.OS !== "web",
  });

  const decisions = usePolling(() => api.decisions(8), 30_000);
  const refreshDecisions = decisions.refresh;

  const symbol = ticker.trim().toUpperCase();
  const qty = Number(quantity);
  const limit = Number(price);
  const valid =
    symbol.length >= 1 && Number.isFinite(qty) && qty > 0 && Number.isFinite(limit) && limit > 0;
  const notional = valid ? qty * limit : 0;

  const fetchMark = useCallback(async () => {
    if (!symbol) return;
    setMarkLoading(true);
    try {
      const prediction = await api.prediction(symbol);
      setPrice(prediction.current_price.toFixed(2));
    } catch {
      // mark lookup is a convenience; the user can type the price manually
    } finally {
      setMarkLoading(false);
    }
  }, [symbol]);

  const stage = () => {
    setSubmitError("");
    if (!valid) {
      setSubmitError("Enter a ticker, a positive quantity, and a limit price.");
      return;
    }
    setConfirming(true);
  };

  const send = async () => {
    if (!valid) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const response = await api.submitOrder({
        ticker: symbol,
        side,
        quantity: qty,
        price: limit,
        order_type: "LIMIT",
        dry_run: dryRun,
        strategy_id: "manual-mobile",
        rationale: `Manual ${side} from StockSense Ops mobile`,
        idempotency_key: newKey(),
      });
      setResult(response);
      setConfirming(false);
      void refreshDecisions();
    } catch (error) {
      const apiError = error as ApiError;
      setSubmitError(`${apiError.code ?? "ERROR"}: ${apiError.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <Animated.ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          onScroll={onScroll}
          scrollEventThrottle={16}
        >
          <View style={styles.header}>
            <View>
              <Text style={styles.eyebrow}>RISK-GATED</Text>
              <Text style={styles.title}>Paper Order</Text>
            </View>
            <Badge label="SIMULATE" tone="info" />
          </View>

          <Reveal scrollY={scrollY} index={0}>
            <Card>
              <SectionHeader title="Order" />
              <Text style={styles.label}>Ticker</Text>
              <TextInput
                value={ticker}
                onChangeText={setTicker}
                autoCapitalize="characters"
                autoCorrect={false}
                placeholder="NVDA"
                placeholderTextColor={colors.faint}
                style={styles.input}
              />

              <Text style={styles.label}>Side</Text>
              <View style={styles.segment}>
                {(["BUY", "SELL"] as Side[]).map((option) => {
                  const active = side === option;
                  return (
                    <Pressable
                      key={option}
                      onPress={() => setSide(option)}
                      style={({ pressed }) => [
                        styles.segmentItem,
                        active && {
                          backgroundColor:
                            option === "BUY" ? colors.accentSoft : colors.dangerSoft,
                          borderColor: option === "BUY" ? colors.accent : colors.danger,
                        },
                        pressed && styles.pressed,
                      ]}
                    >
                      <Text
                        style={[
                          styles.segmentText,
                          active && {
                            color: option === "BUY" ? colors.accent : colors.danger,
                          },
                        ]}
                      >
                        {option}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>

              <View style={styles.fieldRow}>
                <View style={styles.flex}>
                  <Text style={styles.label}>Quantity</Text>
                  <TextInput
                    value={quantity}
                    onChangeText={setQuantity}
                    keyboardType="decimal-pad"
                    placeholder="1"
                    placeholderTextColor={colors.faint}
                    style={styles.input}
                  />
                </View>
                <View style={styles.flex}>
                  <Text style={styles.label}>Limit price</Text>
                  <TextInput
                    value={price}
                    onChangeText={setPrice}
                    keyboardType="decimal-pad"
                    placeholder="0.00"
                    placeholderTextColor={colors.faint}
                    style={styles.input}
                  />
                </View>
              </View>

              <View style={styles.markRow}>
                <Pressable
                  onPress={fetchMark}
                  disabled={markLoading}
                  style={({ pressed }) => [styles.ghostButton, pressed && styles.pressed]}
                >
                  <Text style={styles.ghostText}>
                    {markLoading ? "Fetching…" : "Use current price"}
                  </Text>
                </Pressable>
                <Text style={styles.notional}>Notional {valid ? usd(notional) : "—"}</Text>
              </View>

              <Divider />

              <View style={styles.switchRow}>
                <View style={styles.flex}>
                  <Text style={styles.switchTitle}>Dry run</Text>
                  <Text style={styles.switchSub}>
                    {dryRun
                      ? "Records the decision, sends nothing to the broker."
                      : "Sends a real order to the moomoo paper account."}
                  </Text>
                </View>
                <Switch
                  value={dryRun}
                  onValueChange={setDryRun}
                  trackColor={{ false: colors.dangerSoft, true: colors.accentSoft }}
                  thumbColor={dryRun ? colors.accent : colors.danger}
                />
              </View>

              {submitError ? <Text style={styles.errorText}>{submitError}</Text> : null}

              {!confirming ? (
                <Pressable
                  onPress={stage}
                  style={({ pressed }) => [
                    styles.primaryButton,
                    !valid && styles.primaryDisabled,
                    pressed && valid && styles.pressed,
                  ]}
                >
                  <Text style={styles.primaryText}>Review order</Text>
                </Pressable>
              ) : (
                <View style={styles.confirmBox}>
                  <Text style={styles.confirmTitle}>
                    {dryRun ? "Confirm dry run" : "Confirm live paper order"}
                  </Text>
                  <Text style={styles.confirmText}>
                    {side} {qty} {symbol} @ {usd(limit)} limit · {usd(notional)}
                  </Text>
                  <View style={styles.confirmActions}>
                    <Pressable
                      onPress={() => setConfirming(false)}
                      style={({ pressed }) => [styles.ghostButton, pressed && styles.pressed]}
                    >
                      <Text style={styles.ghostText}>Cancel</Text>
                    </Pressable>
                    <Pressable
                      onPress={send}
                      disabled={submitting}
                      style={({ pressed }) => [
                        styles.primaryButton,
                        styles.primaryFlex,
                        submitting && styles.primaryDisabled,
                        pressed && styles.pressed,
                      ]}
                    >
                      <Text style={styles.primaryText}>
                        {submitting ? "Sending…" : dryRun ? "Record dry run" : "Send order"}
                      </Text>
                    </Pressable>
                  </View>
                </View>
              )}
            </Card>
          </Reveal>

          {result ? (
            <Reveal index={0}>
              <Card style={styles.resultCard}>
                <SectionHeader
                  title="Result"
                  right={
                    <Badge
                      label={
                        result.execution?.status ??
                        (result.decision.approved ? "approved" : "rejected")
                      }
                      tone={
                        result.execution
                          ? executionTone(result.execution.status)
                          : result.decision.approved
                            ? "positive"
                            : "negative"
                      }
                    />
                  }
                />
                <Text style={styles.resultLine}>
                  {result.decision.order.side} {result.decision.order.quantity}{" "}
                  {result.decision.order.ticker} · {usd(result.decision.notional)} notional
                </Text>
                {result.execution ? (
                  <Text style={styles.resultMeta}>
                    {result.execution.message}
                    {result.execution.order_id ? ` · order ${result.execution.order_id}` : ""}
                  </Text>
                ) : null}
                {result.decision.reason_codes.length > 0 ? (
                  <Text style={styles.resultWarn}>
                    Blocked by: {result.decision.reason_codes.join(", ")}
                  </Text>
                ) : null}
                <Text style={styles.resultMeta}>
                  decision {result.decision.decision_id.slice(0, 8)} · ledger{" "}
                  {result.ledger ?? "?"}
                </Text>
                <Divider />
                <Text style={styles.checksTitle}>Risk checks</Text>
                {result.decision.checks.map((check) => (
                  <View key={check.name} style={styles.checkRow}>
                    <View
                      style={[
                        styles.checkDot,
                        { backgroundColor: check.passed ? colors.accent : colors.danger },
                      ]}
                    />
                    <Text style={styles.checkName}>{check.name}</Text>
                    <Text
                      style={[
                        styles.checkDetail,
                        { color: check.passed ? colors.faint : colors.danger },
                      ]}
                      numberOfLines={1}
                    >
                      {check.detail}
                    </Text>
                  </View>
                ))}
              </Card>
            </Reveal>
          ) : null}

          <Reveal scrollY={scrollY} index={1}>
            <Card>
              <SectionHeader
                title="Recent decisions"
                right={<Badge label={decisions.data ? String(decisions.data.count) : "0"} />}
              />
              {decisions.data && decisions.data.decisions.length > 0 ? (
                decisions.data.decisions.map((record, index) => (
                  <View key={`${record.decision_id}-${record.event_type}-${index}`}>
                    {index > 0 ? <Divider /> : null}
                    <View style={styles.decisionRow}>
                      <View style={styles.flex}>
                        <Text style={styles.rowTitle}>
                          {record.side} {record.quantity} {record.ticker}
                        </Text>
                        <Text style={styles.rowSub}>
                          {record.event_type} · {record.status} · {clockTime(record.event_time)}
                          {record.dry_run ? " · dry run" : ""}
                        </Text>
                      </View>
                      <Text style={styles.rowValue}>{usd(record.notional)}</Text>
                    </View>
                  </View>
                ))
              ) : (
                <EmptyState text="No decisions recorded yet." />
              )}
            </Card>
          </Reveal>

          <Text style={styles.footer}>
            Orders route through the backend risk gate. Rejections are logged to the decision
            ledger.
          </Text>
        </Animated.ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
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
  label: {
    color: colors.faint,
    fontSize: 9.5,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    fontWeight: "600",
    marginTop: 5,
  },
  input: {
    backgroundColor: colors.panelAlt,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.sm,
    color: colors.text,
    fontSize: 16,
    fontWeight: "600",
    paddingHorizontal: 12,
    paddingVertical: 11,
  },
  segment: { flexDirection: "row", gap: 8 },
  segmentItem: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.panelAlt,
    alignItems: "center",
  },
  segmentText: { color: colors.muted, fontSize: 12.5, fontWeight: "700", letterSpacing: 0.8 },
  fieldRow: { flexDirection: "row", gap: space.sm },
  markRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  ghostButton: {
    paddingHorizontal: 13,
    paddingVertical: 9,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    backgroundColor: colors.panel,
  },
  ghostText: { color: colors.text, fontSize: 12, fontWeight: "600" },
  notional: { color: colors.faint, fontSize: 12, fontVariant: ["tabular-nums"] },
  switchRow: { flexDirection: "row", alignItems: "center", gap: space.md, paddingVertical: 4 },
  switchTitle: { color: colors.text, fontSize: 14, fontWeight: "600" },
  switchSub: { color: colors.faint, fontSize: 11, marginTop: 2 },
  errorText: { color: colors.danger, fontSize: 12 },
  pressed: { opacity: 0.7 },
  primaryButton: {
    backgroundColor: colors.text,
    borderRadius: radius.sm,
    paddingVertical: 14,
    alignItems: "center",
  },
  primaryFlex: { flex: 1 },
  primaryDisabled: { opacity: 0.3 },
  primaryText: { color: colors.panel, fontSize: 14, fontWeight: "700", letterSpacing: 0.2 },
  confirmBox: {
    gap: 6,
    borderWidth: 1,
    borderColor: colors.warn,
    backgroundColor: colors.warnSoft,
    borderRadius: radius.md,
    padding: space.sm + 2,
  },
  confirmTitle: { color: colors.warn, fontSize: 12, fontWeight: "800", letterSpacing: 0.4 },
  confirmText: { color: colors.text, fontSize: 12 },
  confirmActions: { flexDirection: "row", gap: space.sm, alignItems: "center", marginTop: 5 },
  resultCard: { borderColor: colors.accent },
  resultLine: { color: colors.text, fontSize: 15, fontWeight: "700" },
  resultMeta: { color: colors.faint, fontSize: 11 },
  resultWarn: { color: colors.warn, fontSize: 12 },
  checksTitle: {
    color: colors.faint,
    fontSize: 9.5,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    fontWeight: "600",
  },
  checkRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 3 },
  checkDot: { width: 5, height: 5, borderRadius: 3 },
  checkName: { color: colors.text, fontSize: 12, width: 128 },
  checkDetail: { fontSize: 11, flex: 1 },
  decisionRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 7,
  },
  rowTitle: { color: colors.text, fontSize: 13, fontWeight: "600" },
  rowSub: { color: colors.faint, fontSize: 11 },
  rowValue: { color: colors.text, fontSize: 12, fontVariant: ["tabular-nums"] },
  footer: { color: colors.faint, fontSize: 10, textAlign: "center", marginTop: space.xs },
});
