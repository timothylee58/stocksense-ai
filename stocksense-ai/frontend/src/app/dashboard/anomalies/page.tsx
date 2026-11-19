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
    <div className="min-h-screen" style={{ background: "#F6F4EF" }}>
      {/* Nav */}
      <nav className="sticky top-0 z-40 flex items-center justify-between px-6 py-3"
        style={{ background: "rgba(246,244,239,0.92)", backdropFilter: "blur(14px)", borderBottom: "1px solid rgba(31,94,70,0.06)" }}>
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ background: "#1F5E46", boxShadow: "0 0 8px #1F5E46" }} />
            <span className="serif text-[15px] font-semibold leading-none" style={{ color: "#17191E" }}>StockSense <span className="mono text-[8px] tracking-[0.16em] align-middle" style={{ color: "#9C978D" }}>AI</span></span>
          </Link>
          <Link href="/dashboard" className="mono text-xs opacity-40 hover:opacity-80 transition-opacity" style={{ color: "#3C3E44" }}>/ dashboard</Link>
          <span className="mono text-xs" style={{ color: "#3C3E44" }}>/ anomalies</span>
        </div>
        <button onClick={refetch} className="flex items-center gap-2 px-3 py-1.5 rounded text-xs"
          style={{ background: "rgba(31,94,70,0.06)", border: "1px solid rgba(31,94,70,0.3)", color: "#1F5E46" }}>
          <RefreshCw size={12} />
          <span className="orb tracking-widest">Refresh</span>
        </button>
      </nav>

      <div className="p-5 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="orb text-2xl font-semibold" style={{ color: "#17191E" }}>Anomaly detection</h1>
            <p className="mono text-xs mt-1" style={{ color: "#9C978D" }}>
              Isolation Forest — unsupervised anomaly detection on OHLCV + technical features
            </p>
          </div>
          {data && (
            <div className="flex items-center gap-3">
              <div className="px-4 py-2 rounded-lg"
                style={{ background: "rgba(163,58,49,0.08)", border: "1px solid rgba(163,58,49,0.2)" }}>
                <div className="mono text-xs mb-1" style={{ color: "#9C978D", fontSize: 9 }}>ANOMALIES DETECTED</div>
                <div className="orb text-2xl font-black" style={{ color: "#A33A31" }}>{anomalyCount}</div>
              </div>
              <div className="px-4 py-2 rounded-lg"
                style={{ background: "rgba(66,81,168,0.06)", border: "1px solid rgba(66,81,168,0.15)" }}>
                <div className="mono text-xs mb-1" style={{ color: "#9C978D", fontSize: 9 }}>TOTAL RECORDS</div>
                <div className="orb text-2xl font-black" style={{ color: "#4251A8" }}>{data.records.length}</div>
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
                  background: ticker === t ? "rgba(31,94,70,0.12)" : "#FFFFFF",
                  border: `1px solid ${ticker === t ? "rgba(31,94,70,0.4)" : "rgba(23,25,30,0.10)"}`,
                  color: ticker === t ? "#1F5E46" : "#6E7075",
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
                  background: days === d ? "rgba(66,81,168,0.1)" : "transparent",
                  border: `1px solid ${days === d ? "rgba(66,81,168,0.4)" : "rgba(66,81,168,0.1)"}`,
                  color: days === d ? "#4251A8" : "#6E7075",
                }}
              >
                {d}D
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="p-4 rounded-lg flex items-center gap-3 mono text-sm"
            style={{ background: "rgba(163,58,49,0.08)", border: "1px solid rgba(163,58,49,0.25)", color: "#A33A31" }}>
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
              <div className="mono text-xs mb-4 tracking-widest uppercase" style={{ color: "#9C978D" }}>
                Anomaly scores · {ticker} · {days}d
              </div>
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.records.slice().reverse()} margin={{ left: 0, right: 0 }}>
                    <CartesianGrid strokeDasharray="2 4" stroke="#EFEDE7" vertical={false} />
                    <XAxis dataKey="trading_date" stroke="#D8D3C8" fontSize={9} tickLine={false}
                      interval={Math.floor(data.records.length / 6)} tick={{ fontFamily: "Space Mono", fill: "#9C978D" }} />
                    <YAxis stroke="#D8D3C8" fontSize={9} tickLine={false} axisLine={false}
                      tick={{ fontFamily: "Space Mono", fill: "#9C978D" }} width={40} />
                    <Tooltip
                      contentStyle={{ background: "#FFFFFF", border: "1px solid rgba(31,94,70,0.15)", borderRadius: 8, fontFamily: "Space Mono" }}
                      labelStyle={{ color: "#6E7075", fontSize: 11 }}
                    />
                    <ReferenceLine y={0} stroke="rgba(31,94,70,0.2)" strokeDasharray="3 3" />
                    <Bar dataKey="anomaly_score" radius={[2, 2, 0, 0]}>
                      {data.records.slice().reverse().map((r, i) => (
                        <Cell key={i} fill={r.is_anomaly ? "#A33A31" : "rgba(23,25,30,0.16)"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center gap-4 mt-2 mono text-xs" style={{ color: "#9C978D" }}>
                <span className="flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm inline-block" style={{ background: "#A33A31" }} /> Anomaly detected</span>
                <span className="flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm inline-block" style={{ background: "rgba(23,25,30,0.16)" }} /> Normal</span>
              </div>
            </div>

            {/* Anomaly table */}
            <div className="card p-5">
              <div className="mono text-xs mb-4 tracking-widest uppercase" style={{ color: "#9C978D" }}>
                Anomaly history
              </div>
              <div className="overflow-x-auto">
                <table className="w-full mono text-xs">
                  <thead>
                    <tr style={{ color: "#9C978D", borderBottom: "1px solid rgba(23,25,30,0.08)" }}>
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
                            borderBottom: "1px solid rgba(23,25,30,0.05)",
                            background: r.is_anomaly ? "rgba(163,58,49,0.04)" : "transparent",
                          }}
                        >
                          <td className="py-2 pr-4" style={{ color: "#3C3E44" }}>{r.trading_date}</td>
                          <td className="py-2 pr-4" style={{ color: "#3C3E44" }}>${r.price_close?.toFixed(2) ?? "—"}</td>
                          <td className="py-2 pr-4" style={{ color: r.anomaly_score < -0.1 ? "#A33A31" : "#6E7075" }}>
                            {r.anomaly_score?.toFixed(4) ?? "—"}
                          </td>
                          <td className="py-2 pr-4" style={{ color: (r.daily_return ?? 0) >= 0 ? "#1F5E46" : "#A33A31" }}>
                            {r.daily_return != null ? ((r.daily_return ?? 0) * 100).toFixed(2) + "%" : "—"}
                          </td>
                          <td className="py-2 pr-4" style={{ color: "#6E7075" }}>{r.bb_width?.toFixed(4) ?? "—"}</td>
                          <td className="py-2 pr-4" style={{ color: Math.abs(r.volume_zscore ?? 0) > 2 ? "#8A6430" : "#6E7075" }}>
                            {r.volume_zscore?.toFixed(2) ?? "—"}
                          </td>
                          <td className="py-2 pr-4">
                            {r.is_anomaly ? (
                              <motion.span
                                animate={{ boxShadow: ["0 0 0 0 rgba(163,58,49,0)", "0 0 0 4px rgba(163,58,49,0.3)", "0 0 0 0 rgba(163,58,49,0)"] }}
                                transition={{ duration: 1.5, repeat: Infinity }}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs"
                                style={{ background: "rgba(163,58,49,0.12)", color: "#A33A31", border: "1px solid rgba(163,58,49,0.3)" }}
                              >
                                <Activity size={10} /> ANOMALY
                              </motion.span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-xs" style={{ color: "#9C978D", background: "rgba(23,25,30,0.04)" }}>
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
