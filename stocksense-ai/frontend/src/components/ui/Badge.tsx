"use client";

import React from "react";

type BadgeVariant = "up" | "down" | "neutral" | "info" | "warning" | "demo";

const VARIANT_STYLES: Record<BadgeVariant, { color: string; bg: string; border: string }> = {
  up:      { color: "#00ffcc", bg: "rgba(0,255,204,0.10)", border: "rgba(0,255,204,0.25)" },
  down:    { color: "#ff4560", bg: "rgba(255,69,96,0.10)",  border: "rgba(255,69,96,0.25)" },
  neutral: { color: "#94a3b8", bg: "rgba(148,163,184,0.08)", border: "rgba(148,163,184,0.2)" },
  info:    { color: "#60a5fa", bg: "rgba(96,165,250,0.10)", border: "rgba(96,165,250,0.25)" },
  warning: { color: "#f5a623", bg: "rgba(245,166,35,0.10)", border: "rgba(245,166,35,0.25)" },
  demo:    { color: "#a78bfa", bg: "rgba(167,139,250,0.10)", border: "rgba(167,139,250,0.25)" },
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
        gap: 4,
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        color: s.color,
        background: s.bg,
        border: `1px solid ${s.border}`,
        fontFamily: "'Share Tech Mono', monospace",
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
            boxShadow: `0 0 4px ${s.color}`,
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
