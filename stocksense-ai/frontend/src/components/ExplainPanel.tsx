"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { RefreshCw, HelpCircle, ChevronDown, ChevronUp } from "lucide-react";
import { Skeleton, SkeletonLine } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ShapFeature {
  feature: string;
  value: number;
  contribution: number;
}

interface ExplainData {
  ticker: string;
  prediction: string;
  probability: number;
  expected_value: number;
  top_features: ShapFeature[];
  demo?: boolean;
}

function prettyName(f: string): string {
  return f
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace("Rsi", "RSI")
    .replace("Macd", "MACD")
    .replace("Bb ", "BB ")
    .replace("Ema", "EMA")
    .replace("Sma", "SMA")
    .replace("Atr", "ATR")
    .replace("Roc", "ROC");
}

function ContributionBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(1, Math.abs(value) / max) : 0;
  const color = value >= 0 ? "#00ffcc" : "#ff4560";
  const shadow = value >= 0 ? "0 0 6px rgba(0,255,204,0.4)" : "0 0 6px rgba(255,69,96,0.4)";
  return (
    <div style={{ position: "relative", height: 10, borderRadius: 5, background: "rgba(255,255,255,0.04)", overflow: "hidden" }}>
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${pct * 100}%` }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        style={{
          position: "absolute",
          top: 0, bottom: 0,
          right: value < 0 ? 0 : undefined,
          left: value >= 0 ? 0 : undefined,
          background: color,
          boxShadow: shadow,
          borderRadius: 5,
        }}
      />
    </div>
  );
}

export default function ExplainPanel({ ticker }: { ticker: string }) {
  const [data, setData] = useState<ExplainData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const fetch_ = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API_URL}/api/explain/${ticker}`);
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      setData(await r.json());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => { fetch_(); }, [fetch_]);

  const maxContrib = data ? Math.max(...data.top_features.map((f) => Math.abs(f.contribution))) : 1;
  const shown = expanded ? data?.top_features : data?.top_features.slice(0, 6);

  return (
    <div className="card p-5 mt-4" style={{ background: "rgba(0,12,28,0.8)", border: "1px solid rgba(0,153,255,0.1)", borderRadius: 12 }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <HelpCircle size={14} style={{ color: "#60a5fa" }} />
          <span className="orb text-xs font-bold tracking-widest" style={{ color: "#60a5fa" }}>
            WHY DID IT PREDICT THIS?
          </span>
          {data?.demo && <Badge variant="demo" dot>DEMO</Badge>}
        </div>
        <button
          onClick={fetch_}
          disabled={loading}
          className="flex items-center gap-1 px-2 py-1 rounded"
          style={{ fontSize: 10, color: "#2a5070", border: "1px solid rgba(0,153,255,0.1)", background: "transparent", cursor: "pointer" }}
        >
          <RefreshCw size={10} className={loading ? "animate-spin" : ""} />
          REFRESH
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <SkeletonLine width="30%" />
              <div style={{ flex: 1 }}><Skeleton height={10} radius={5} /></div>
              <SkeletonLine width="10%" />
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="text-center py-4" style={{ color: "#ff4560", fontSize: 12 }}>
          {error.includes("404") ? "No trained model — run `make train` first." : error}
        </div>
      )}

      {/* Content */}
      {!loading && data && (
        <>
          {/* Summary row */}
          <div className="flex items-center gap-3 mb-4 pb-3" style={{ borderBottom: "1px solid rgba(0,153,255,0.08)" }}>
            <span className="mono text-xs" style={{ color: "#2a5070" }}>BASE RATE</span>
            <span className="mono text-xs" style={{ color: "#94a3b8" }}>{(data.expected_value * 100).toFixed(1)}%</span>
            <span className="mono text-xs" style={{ color: "#2a5070" }}>→</span>
            <span className="mono text-xs" style={{ color: "#94a3b8" }}>FINAL</span>
            <span className="mono text-xs font-bold" style={{ color: data.prediction === "UP" ? "#00ffcc" : "#ff4560" }}>
              {(data.probability * 100).toFixed(1)}% {data.prediction}
            </span>
            <span className="mono text-xs" style={{ color: "#2a5070", marginLeft: "auto" }}>SHAP · XGBoost</span>
          </div>

          {/* Legend */}
          <div className="flex items-center gap-4 mb-3" style={{ fontSize: 9, color: "#2a5070" }}>
            <span className="flex items-center gap-1"><span style={{ width: 8, height: 8, borderRadius: 2, background: "#00ffcc", display: "inline-block" }} /> Bullish push</span>
            <span className="flex items-center gap-1"><span style={{ width: 8, height: 8, borderRadius: 2, background: "#ff4560", display: "inline-block" }} /> Bearish push</span>
          </div>

          {/* Feature rows */}
          <AnimatePresence>
            <div className="space-y-2.5">
              {shown?.map((f, i) => (
                <motion.div
                  key={f.feature}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="grid gap-2"
                  style={{ gridTemplateColumns: "140px 1fr 56px 48px", alignItems: "center" }}
                >
                  <span className="mono truncate" style={{ fontSize: 10, color: "#94a3b8" }} title={prettyName(f.feature)}>
                    {prettyName(f.feature)}
                  </span>
                  <ContributionBar value={f.contribution} max={maxContrib} />
                  <span className="mono text-right" style={{ fontSize: 10, color: f.contribution >= 0 ? "#00ffcc" : "#ff4560" }}>
                    {f.contribution >= 0 ? "+" : ""}{f.contribution.toFixed(3)}
                  </span>
                  <span className="mono text-right" style={{ fontSize: 10, color: "#2a5070" }}>
                    {Number.isInteger(f.value) ? f.value : f.value.toFixed(2)}
                  </span>
                </motion.div>
              ))}
            </div>
          </AnimatePresence>

          {/* Show more */}
          {data.top_features.length > 6 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 mt-3 w-full justify-center"
              style={{ fontSize: 10, color: "#2a5070", background: "transparent", border: "none", cursor: "pointer" }}
            >
              {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {expanded ? "Show fewer" : `Show ${data.top_features.length - 6} more features`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
