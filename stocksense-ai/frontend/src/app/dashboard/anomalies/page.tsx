"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
import { AlertTriangle, RefreshCw, Activity } from "lucide-react";
import Link from "next/link";
import { useAnomalies } from "@/hooks/useAnomalies";
import { STOCKS } from "@/lib/constants";

const TICKERS = STOCKS.map((s) => s.ticker);

function Skeleton({ className }: { className?: string }) {
  return (
    <motion.div
      className={`rounded bg-white/5 ${className ?? ""}`}
      animate={{ opacity: [0.4, 0.8, 0.4] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
    />
  );
}

export default function AnomaliesPage() {
  const [ticker, setTicker] = useState("NVDA");
  const [days, setDays] = useState(30);
  const { data, loading, error, refetch } = useAnomalies(ticker, days);

  const anomalyCount = data?.records.filter((r) => r.is_anomaly).length ?? 0;

  return (
    <div className="min-h-screen" style={{ background: "#030d1a", fontFamily: "Share Tech Mono, monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');
        .orb { font-family: 'Orbitron', monospace; }
        .mono { font-family: 'Share Tech Mono', monospace; }
        .card { background: rgba(0,12,28,0.8); border: 1px solid rgba(0,153,255,0.1); border-radius: 12px; }
      `}</style>

      {/* Nav */}
      <nav className="sticky top-0 z-40 flex items-center justify-between px-6 py-3"
        style={{ background: "rgba(3,13,26,0.92)", backdropFilter: "blur(14px)", borderBottom: "1px solid rgba(0,255,200,0.06)" }}>
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ background: "#00ffcc", boxShadow: "0 0 8px #00ffcc" }} />
            <span className="orb text-xs font-bold tracking-widest" style={{ color: "#00ffcc" }}>STOCKSENSE AI</span>
          </Link>
          <Link href="/dashboard" className="mono text-xs opacity-40 hover:opacity-80 transition-opacity" style={{ color: "#c8e0f4" }}>/ dashboard</Link>
          <span className="mono text-xs" style={{ color: "#c8e0f4" }}>/ anomalies</span>
        </div>
        <button onClick={refetch} className="flex items-center gap-2 px-3 py-1.5 rounded text-xs"
          style={{ background: "rgba(0,255,200,0.06)", border: "1px solid rgba(0,255,200,0.3)", color: "#00ffcc" }}>
          <RefreshCw size={12} />
          <span className="orb tracking-widest">REFRESH</span>
        </button>
      </nav>

      <div className="p-5 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="orb text-xl font-black" style={{ color: "#00ffcc" }}>ANOMALY DETECTION</h1>
            <p className="mono text-xs mt-1" style={{ color: "#2a5070" }}>
              Isolation Forest — unsupervised anomaly detection on OHLCV + technical features
            </p>
          </div>
          {data && (
            <div className="flex items-center gap-3">
              <div className="px-4 py-2 rounded-lg"
                style={{ background: "rgba(255,69,96,0.08)", border: "1px solid rgba(255,69,96,0.2)" }}>
                <div className="mono text-xs mb-1" style={{ color: "#2a5070", fontSize: 9 }}>ANOMALIES DETECTED</div>
                <div className="orb text-2xl font-black" style={{ color: "#ff4560" }}>{anomalyCount}</div>
              </div>
              <div className="px-4 py-2 rounded-lg"
                style={{ background: "rgba(0,153,255,0.06)", border: "1px solid rgba(0,153,255,0.15)" }}>
                <div className="mono text-xs mb-1" style={{ color: "#2a5070", fontSize: 9 }}>TOTAL RECORDS</div>
                <div className="orb text-2xl font-black" style={{ color: "#0099ff" }}>{data.records.length}</div>
              </div>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex gap-2">
            {TICKERS.slice(0, 6).map((t) => (
              <button
                key={t}
                onClick={() => setTicker(t)}
                className="orb text-xs px-3 py-1.5 rounded transition-all"
                style={{
                  background: ticker === t ? "rgba(0,255,200,0.12)" : "rgba(0,12,28,0.8)",
                  border: `1px solid ${ticker === t ? "rgba(0,255,200,0.4)" : "rgba(0,153,255,0.08)"}`,
                  color: ticker === t ? "#00ffcc" : "#4a7090",
                }}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            {[7, 14, 30, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className="mono text-xs px-3 py-1.5 rounded transition-all"
                style={{
                  background: days === d ? "rgba(0,153,255,0.1)" : "transparent",
                  border: `1px solid ${days === d ? "rgba(0,153,255,0.4)" : "rgba(0,153,255,0.1)"}`,
                  color: days === d ? "#0099ff" : "#4a7090",
                }}
              >
                {d}D
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="p-4 rounded-lg flex items-center gap-3 mono text-sm"
            style={{ background: "rgba(255,69,96,0.08)", border: "1px solid rgba(255,69,96,0.25)", color: "#ff8080" }}>
            <AlertTriangle size={16} />
            {error}
          </div>
        )}

        {loading ? (
          <div className="space-y-4">
            <div className="card p-5"><Skeleton className="h-[200px] w-full" /></div>
            <div className="card p-5"><Skeleton className="h-[300px] w-full" /></div>
          </div>
        ) : data ? (
          <>
            {/* Anomaly score chart */}
            <div className="card p-5">
              <div className="mono text-xs mb-4 tracking-widest" style={{ color: "rgba(0,255,200,0.4)" }}>
                // ISOLATION FOREST ANOMALY SCORES — {ticker} ({days}D)
              </div>
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.records.slice().reverse()} margin={{ left: 0, right: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,255,200,0.04)" vertical={false} />
                    <XAxis dataKey="trading_date" stroke="#1a3a5c" fontSize={9} tickLine={false}
                      interval={Math.floor(data.records.length / 6)} tick={{ fontFamily: "Share Tech Mono" }} />
                    <YAxis stroke="#1a3a5c" fontSize={9} tickLine={false} axisLine={false}
                      tick={{ fontFamily: "Share Tech Mono" }} width={40} />
                    <Tooltip
                      contentStyle={{ background: "#010816", border: "1px solid rgba(0,255,200,0.15)", borderRadius: 8, fontFamily: "Share Tech Mono" }}
                      labelStyle={{ color: "#4a7090", fontSize: 11 }}
                    />
                    <ReferenceLine y={0} stroke="rgba(0,255,200,0.2)" strokeDasharray="3 3" />
                    <Bar dataKey="anomaly_score" radius={[2, 2, 0, 0]}>
                      {data.records.slice().reverse().map((r, i) => (
                        <Cell key={i} fill={r.is_anomaly ? "#ff4560" : "rgba(0,153,255,0.4)"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center gap-4 mt-2 mono text-xs" style={{ color: "#2a5070" }}>
                <span className="flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm inline-block" style={{ background: "#ff4560" }} /> Anomaly detected</span>
                <span className="flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm inline-block" style={{ background: "rgba(0,153,255,0.4)" }} /> Normal</span>
              </div>
            </div>

            {/* Anomaly table */}
            <div className="card p-5">
              <div className="mono text-xs mb-4 tracking-widest" style={{ color: "rgba(0,255,200,0.4)" }}>
                // ANOMALY HISTORY TABLE
              </div>
              <div className="overflow-x-auto">
                <table className="w-full mono text-xs">
                  <thead>
                    <tr style={{ color: "#2a5070", borderBottom: "1px solid rgba(0,153,255,0.1)" }}>
                      {["DATE", "CLOSE", "ANOMALY SCORE", "DAILY RETURN", "BB WIDTH", "VOL Z-SCORE", "STATUS"].map((h) => (
                        <th key={h} className="text-left py-2 pr-4" style={{ fontSize: 9, letterSpacing: "0.1em" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <AnimatePresence>
                      {data.records.map((r, i) => (
                        <motion.tr
                          key={r.trading_date}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.02, duration: 0.2 }}
                          style={{
                            borderBottom: "1px solid rgba(0,153,255,0.04)",
                            background: r.is_anomaly ? "rgba(255,69,96,0.04)" : "transparent",
                          }}
                        >
                          <td className="py-2 pr-4" style={{ color: "#c8e0f4" }}>{r.trading_date}</td>
                          <td className="py-2 pr-4" style={{ color: "#c8e0f4" }}>${r.price_close?.toFixed(2) ?? "—"}</td>
                          <td className="py-2 pr-4" style={{ color: r.anomaly_score < -0.1 ? "#ff4560" : "#4a7090" }}>
                            {r.anomaly_score?.toFixed(4) ?? "—"}
                          </td>
                          <td className="py-2 pr-4" style={{ color: (r.daily_return ?? 0) >= 0 ? "#00ffcc" : "#ff4560" }}>
                            {r.daily_return != null ? ((r.daily_return ?? 0) * 100).toFixed(2) + "%" : "—"}
                          </td>
                          <td className="py-2 pr-4" style={{ color: "#4a7090" }}>{r.bb_width?.toFixed(4) ?? "—"}</td>
                          <td className="py-2 pr-4" style={{ color: Math.abs(r.volume_zscore ?? 0) > 2 ? "#f5a623" : "#4a7090" }}>
                            {r.volume_zscore?.toFixed(2) ?? "—"}
                          </td>
                          <td className="py-2 pr-4">
                            {r.is_anomaly ? (
                              <motion.span
                                animate={{ boxShadow: ["0 0 0 0 rgba(255,69,96,0)", "0 0 0 4px rgba(255,69,96,0.3)", "0 0 0 0 rgba(255,69,96,0)"] }}
                                transition={{ duration: 1.5, repeat: Infinity }}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs"
                                style={{ background: "rgba(255,69,96,0.12)", color: "#ff4560", border: "1px solid rgba(255,69,96,0.3)" }}
                              >
                                <Activity size={10} /> ANOMALY
                              </motion.span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-xs" style={{ color: "#2a5070", background: "rgba(0,153,255,0.05)" }}>
                                NORMAL
                              </span>
                            )}
                          </td>
                        </motion.tr>
                      ))}
                    </AnimatePresence>
                  </tbody>
                </table>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
