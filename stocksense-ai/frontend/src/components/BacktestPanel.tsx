"use client";

import React, { useCallback, useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { motion } from "framer-motion";
import { BarChart3, RefreshCw } from "lucide-react";
import { Skeleton, SkeletonLine } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface BacktestMetrics {
  total_return: number;
  benchmark_return: number;
  alpha: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown: number;
  win_rate: number;
  n_trades: number;
  annualised_return: number;
}

interface BacktestData {
  ticker: string;
  test_period: { start: string; end: string; n_days: number };
  metrics: BacktestMetrics;
  equity_curve: { date: string; strategy: number; benchmark: number }[];
  demo?: boolean;
}

function pct(v: number) { return `${(v * 100).toFixed(1)}%`; }
function sign(v: number) { return v >= 0 ? "+" : ""; }

function MetricCell({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5 px-3 py-2 rounded"
      style={{ background: "rgba(0,153,255,0.04)", border: "1px solid rgba(0,153,255,0.06)" }}>
      <span className="mono" style={{ fontSize: 9, color: "#2a5070", letterSpacing: "0.1em" }}>{label}</span>
      <span className="mono font-bold" style={{ fontSize: 13, color: color ?? "#e2f0ff" }}>{value}</span>
    </div>
  );
}

// Custom tooltip for equity curve
function EqTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const strat = payload.find((p: any) => p.dataKey === "strategy");
  const bench = payload.find((p: any) => p.dataKey === "benchmark");
  return (
    <div className="rounded px-3 py-2" style={{ background: "rgba(3,13,26,0.95)", border: "1px solid rgba(0,153,255,0.2)", fontSize: 11 }}>
      <div className="mono" style={{ color: "#2a5070", marginBottom: 4 }}>{label}</div>
      {strat && <div className="mono" style={{ color: "#00ffcc" }}>Strategy: {((strat.value - 1) * 100).toFixed(2)}%</div>}
      {bench && <div className="mono" style={{ color: "#60a5fa" }}>Benchmark: {((bench.value - 1) * 100).toFixed(2)}%</div>}
    </div>
  );
}

export default function BacktestPanel({ ticker }: { ticker: string }) {
  const [data, setData] = useState<BacktestData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch_ = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API_URL}/api/backtest/${ticker}`);
      if (!r.ok) throw new Error(`${r.status} — ${(await r.json()).detail ?? r.statusText}`);
      setData(await r.json());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => { fetch_(); }, [fetch_]);

  const m = data?.metrics;
  const alphaPct = m ? sign(m.alpha) + pct(m.alpha) : "";
  const retPct   = m ? sign(m.total_return) + pct(m.total_return) : "";

  return (
    <div className="card p-5 mt-4" style={{ background: "rgba(0,12,28,0.8)", border: "1px solid rgba(0,153,255,0.1)", borderRadius: 12 }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 size={14} style={{ color: "#a78bfa" }} />
          <span className="orb text-xs font-bold tracking-widest" style={{ color: "#a78bfa" }}>
            WALK-FORWARD BACKTEST
          </span>
          {data?.demo && <Badge variant="demo" dot>DEMO</Badge>}
          {data && (
            <span className="mono" style={{ fontSize: 9, color: "#2a5070" }}>
              {data.test_period.start.slice(0, 10)} → {data.test_period.end.slice(0, 10)}
              &nbsp;({data.test_period.n_days}d)
            </span>
          )}
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
        <div>
          <div className="flex gap-2 mb-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} style={{ flex: 1 }}>
                <Skeleton height={52} radius={6} />
              </div>
            ))}
          </div>
          <Skeleton height={140} radius={8} />
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="text-center py-4" style={{ color: "#ff4560", fontSize: 12 }}>
          {error.includes("422") ? "No trained model — run `make train` first." : error}
        </div>
      )}

      {/* Content */}
      {!loading && data && m && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          {/* Metrics grid */}
          <div className="grid grid-cols-5 gap-2 mb-4">
            <MetricCell
              label="TOTAL RETURN"
              value={retPct}
              color={m.total_return >= 0 ? "#00ffcc" : "#ff4560"}
            />
            <MetricCell
              label="ALPHA vs B&H"
              value={alphaPct}
              color={m.alpha >= 0 ? "#00ffcc" : "#ff4560"}
            />
            <MetricCell
              label="SHARPE"
              value={m.sharpe_ratio.toFixed(2)}
              color={m.sharpe_ratio >= 1 ? "#00ffcc" : m.sharpe_ratio >= 0 ? "#f5a623" : "#ff4560"}
            />
            <MetricCell
              label="MAX DRAWDOWN"
              value={pct(m.max_drawdown)}
              color={m.max_drawdown > -0.1 ? "#00ffcc" : m.max_drawdown > -0.2 ? "#f5a623" : "#ff4560"}
            />
            <MetricCell label="WIN RATE" value={pct(m.win_rate)} />
          </div>

          <div className="flex gap-2 mb-4">
            <MetricCell label="SORTINO"  value={m.sortino_ratio.toFixed(2)} />
            <MetricCell label="CALMAR"   value={m.calmar_ratio.toFixed(2)} />
            <MetricCell label="N TRADES" value={String(m.n_trades)} />
            <MetricCell label="ANN RETURN" value={sign(m.annualised_return) + pct(m.annualised_return)} />
          </div>

          {/* Equity curve */}
          <div style={{ marginTop: 12 }}>
            <span className="mono" style={{ fontSize: 9, color: "#2a5070", letterSpacing: "0.1em" }}>
              EQUITY CURVE — long-only strategy vs buy &amp; hold
            </span>
            <div style={{ height: 140, marginTop: 6 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.equity_curve} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 8, fill: "#2a5070" }}
                    tickFormatter={(d) => d?.slice(5, 10) ?? ""}
                    interval="preserveStartEnd"
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 8, fill: "#2a5070" }}
                    tickFormatter={(v) => `${((v - 1) * 100).toFixed(0)}%`}
                    axisLine={false}
                    tickLine={false}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip content={<EqTooltip />} />
                  <ReferenceLine y={1} stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                  <Line
                    dataKey="strategy"
                    stroke="#00ffcc"
                    strokeWidth={1.5}
                    dot={false}
                    name="Strategy"
                  />
                  <Line
                    dataKey="benchmark"
                    stroke="#60a5fa"
                    strokeWidth={1}
                    strokeDasharray="4 2"
                    dot={false}
                    name="Benchmark"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="flex items-center gap-4 mt-1" style={{ fontSize: 9, color: "#2a5070" }}>
              <span className="flex items-center gap-1">
                <span style={{ width: 16, height: 2, background: "#00ffcc", display: "inline-block" }} />
                Strategy
              </span>
              <span className="flex items-center gap-1">
                <span style={{ width: 16, height: 2, background: "#60a5fa", display: "inline-block", borderTop: "2px dashed #60a5fa" }} />
                Buy &amp; Hold
              </span>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}
