"use client";

import React from "react";

type BadgeVariant = "up" | "down" | "neutral" | "info" | "warning" | "demo";

const VARIANT_STYLES: Record<BadgeVariant, { color: string; bg: string; border: string }> = {
  up:      { color: "#1F5E46", bg: "#E9F1EC", border: "#CFE0D5" },
  down:    { color: "#A33A31", bg: "#F9EBE8", border: "#EBD2CD" },
  neutral: { color: "#6E7075", bg: "#F6F4EF", border: "#E6E2D9" },
  info:    { color: "#4251A8", bg: "#ECEEF9", border: "#DADDF2" },
  warning: { color: "#8A6430", bg: "#F7EFE1", border: "#E7D9BE" },
  demo:    { color: "#6B5CA5", bg: "#F0EDF7", border: "#DED8ED" },
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
  /** Optional dot indicator shown before the label. */
  dot?: boolean;
}

/**
 * Small coloured label for statuses, tags, and flags.
 * Variant "demo" renders a purple pill indicating demo/synthetic data.
 */
export function Badge({ variant = "neutral", children, className = "", dot = false }: BadgeProps) {
  const s = VARIANT_STYLES[variant];
  return (
    <span
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "3px 9px",
        borderRadius: 999,
        fontSize: 9,
        fontWeight: 600,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: s.color,
        background: s.bg,
        border: `1px solid ${s.border}`,
        fontFamily: "var(--font-mono), monospace",
        whiteSpace: "nowrap",
      }}
    >
      {dot && (
        <span
          style={{
            width: 5,
            height: 5,
            borderRadius: "50%",
            background: s.color,
            flexShrink: 0,
          }}
        />
      )}
      {children}
    </span>
  );
}

/** Convenience badge that derives variant from a numeric change percentage. */
export function ChangeBadge({ pct }: { pct: number }) {
  const variant: BadgeVariant = pct > 0 ? "up" : pct < 0 ? "down" : "neutral";
  const sign = pct > 0 ? "+" : "";
  return <Badge variant={variant}>{sign}{pct.toFixed(2)}%</Badge>;
}

export default Badge;
