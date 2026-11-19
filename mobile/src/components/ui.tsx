import type { ReactNode } from "react";
import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from "react-native";

import { colors, fonts, radius, shadow, space } from "@/lib/theme";

type Tone = "neutral" | "positive" | "negative" | "warning" | "info";

const toneColors: Record<Tone, { fg: string; bg: string }> = {
  neutral: { fg: colors.muted, bg: "#F1EFE9" },
  positive: { fg: colors.accent, bg: colors.accentSoft },
  negative: { fg: colors.danger, bg: colors.dangerSoft },
  warning: { fg: colors.warn, bg: colors.warnSoft },
  info: { fg: colors.info, bg: colors.infoSoft },
};

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Badge({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  const palette = toneColors[tone];
  return (
    <View style={[styles.badge, { backgroundColor: palette.bg }]}>
      <Text style={[styles.badgeText, { color: palette.fg }]}>{label}</Text>
    </View>
  );
}

export function Metric({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: Tone;
}) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color: tone === "neutral" ? colors.text : toneColors[tone].fg }]}>
        {value}
      </Text>
      {sub ? <Text style={styles.metricSub}>{sub}</Text> : null}
    </View>
  );
}

export function SectionHeader({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {right}
    </View>
  );
}

export function EmptyState({ text }: { text: string }) {
  return <Text style={styles.empty}>{text}</Text>;
}

export function Divider() {
  return <View style={styles.divider} />;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.panel,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space.md + 2,
    gap: space.sm,
    ...shadow,
  },
  badge: {
    alignSelf: "flex-start",
    paddingHorizontal: 9,
    paddingVertical: 3,
    borderRadius: 999,
  },
  badgeText: {
    fontSize: 9.5,
    fontWeight: "700",
    letterSpacing: 0.9,
    textTransform: "uppercase",
  },
  metric: {
    flexGrow: 1,
    flexBasis: "45%",
    gap: 5,
    paddingVertical: 4,
  },
  metricLabel: {
    color: colors.faint,
    fontSize: 9.5,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    fontWeight: "600",
  },
  metricValue: {
    fontFamily: fonts.sans,
    fontSize: 21,
    fontWeight: "600",
    letterSpacing: -0.3,
    fontVariant: ["tabular-nums"],
  },
  metricSub: {
    color: colors.faint,
    fontSize: 11,
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  sectionTitle: {
    color: colors.muted,
    fontFamily: fonts.sans,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.6,
    textTransform: "uppercase",
  },
  empty: {
    color: colors.faint,
    fontSize: 12,
    paddingVertical: 8,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
  },
});
