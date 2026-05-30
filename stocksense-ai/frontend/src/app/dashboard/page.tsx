"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ComposedChart, Line,
} from "recharts";
import { AnimatePresence, motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus, Activity, BarChart3,
         RefreshCw, AlertTriangle, ChevronRight, Upload, CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { PredictionResponse, StockInfo } from "@/types/stock";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Stock universe (mirrors backend) ─────────────────────────────────────────
const STOCKS: StockInfo[] = [
  { ticker: "AAPL",  name: "Apple",         sector: "Technology" },
  { ticker: "NVDA",  name: "NVIDIA",        sector: "Technology" },
  { ticker: "MSFT",  name: "Microsoft",     sector: "Technology" },
  { ticker: "AMZN",  name: "Amazon",        sector: "Consumer" },
  { ticker: "GOOGL", name: "Alphabet",      sector: "Communication" },
  { ticker: "META",  name: "Meta",          sector: "Communication" },
  { ticker: "TSLA",  name: "Tesla",         sector: "Automotive" },
  { ticker: "BRK-B", name: "Berkshire",     sector: "Financials" },
  { ticker: "LLY",   name: "Eli Lilly",     sector: "Healthcare" },
  { ticker: "JPM",   name: "JPMorgan",      sector: "Financials" },
  { ticker: "V",     name: "Visa",          sector: "Financials" },
  { ticker: "WMT",   name: "Walmart",       sector: "Retail" },
  { ticker: "XOM",   name: "ExxonMobil",    sector: "Energy" },
  { ticker: "NFLX",  name: "Netflix",       sector: "Media" },
  { ticker: "AMD",   name: "AMD",           sector: "Technology" },
];

// ── Color helpers ─────────────────────────────────────────────────────────────
const SIG_COLOR: Record<string, string> = {
  BUY: "#00ffcc", SELL: "#ff4560", HOLD: "#f5a623",
};
const TREND_COLOR: Record<string, string> = {
  BULLISH: "#00ffcc", BEARISH: "#ff4560", SIDEWAYS: "#f5a623",
};
const ACTION_COLOR: Record<string, string> = {
  BUY_NOW: "#00ffcc", WAIT_FOR_DIP: "#0099ff", HOLD: "#f5a623",
  SELL_NOW: "#ff4560", AVOID: "#ff6b35",
};
const RISK_COLOR: Record<string, string> = {
  LOW: "#00ffcc", MEDIUM: "#f5a623", HIGH: "#ff4560",
};

function pct(v: number) { return (v >= 0 ? "+" : "") + v.toFixed(2) + "%"; }
function $$(v: number | null | undefined) { return v != null ? "$" + v.toFixed(2) : "—"; }
function score10Color(s: number) {
  if (s >= 7) return "#00ffcc";
  if (s >= 5) return "#f5a623";
  return "#ff4560";
}

// ── Mini sparkline (SVG path) ─────────────────────────────────────────────────
function Spark({ values, color }: { values: number[]; color: string }) {
  if (!values.length) return null;
  const W = 80, H = 28;
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * W;
    const y = H - ((v - min) / range) * H;
    return `${x},${y}`;
  });
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

// ── Timing score gauge ────────────────────────────────────────────────────────
function TimingGauge({ score }: { score: number }) {
  const col = score10Color(score);
  const pct = (score / 10) * 100;
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-28 h-28">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" />
          <circle
            cx="50" cy="50" r="42"
            fill="none"
            stroke={col}
            strokeWidth="10"
            strokeDasharray={`${2 * Math.PI * 42 * pct / 100} ${2 * Math.PI * 42 * (1 - pct / 100)}`}
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 6px ${col})`, transition: "stroke-dasharray 0.8s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-black text-2xl" style={{ color: col, fontFamily: "Orbitron, monospace" }}>
            {score.toFixed(1)}
          </span>
          <span className="text-xs opacity-50" style={{ fontFamily: "Share Tech Mono, monospace" }}>/10</span>
        </div>
      </div>
      <span className="text-xs tracking-widest" style={{ fontFamily: "Share Tech Mono, monospace", color: col, opacity: 0.8 }}>
        TIMING SCORE
      </span>
    </div>
  );
}

type FlowState = "idle" | "uploading" | "success" | "error";

function ProgressFlowState({
  state,
  progress,
}: {
  state: FlowState;
  progress: number;
}) {
  return (
    <div className="relative w-44 h-10">
      <AnimatePresence mode="wait">
        {state === "idle" && (
          <motion.div
            key="idle"
            layout
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="absolute inset-0 flex items-center justify-center gap-2 rounded-md border"
            style={{ borderColor: "rgba(0,255,200,0.2)", background: "rgba(0,255,200,0.05)", color: "#00ffcc" }}
          >
            <Upload size={14} />
            <span className="mono text-[10px] tracking-widest">IDLE</span>
          </motion.div>
        )}

        {state === "uploading" && (
          <motion.div
            key="uploading"
            layout
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="absolute inset-0 rounded-md border px-2 py-1.5"
            style={{ borderColor: "rgba(167,139,250,0.3)", background: "rgba(167,139,250,0.08)" }}
          >
            <div className="flex items-center justify-between text-[10px] mono mb-1" style={{ color: "#d5c9ff" }}>
              <span className="tracking-widest">UPLOADING</span>
              <span>{Math.round(progress)}%</span>
            </div>
            <div className="h-1 w-full rounded-full" style={{ background: "rgba(255,255,255,0.15)" }}>
              <motion.div
                animate={{ width: `${progress}%` }}
                transition={{ ease: "easeOut" }}
                className="h-1 bg-purple-500 rounded-full"
              />
            </div>
          </motion.div>
        )}

        {state === "success" && (
          <motion.div
            key="success"
            layout
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
            className="absolute inset-0 flex items-center justify-center gap-2 rounded-md border"
            style={{ borderColor: "rgba(0,255,200,0.35)", background: "rgba(0,255,200,0.08)", color: "#00ffcc" }}
          >
            <CheckCircle2 size={14} />
            <span className="mono text-[10px] tracking-widest">SUCCESS</span>
          </motion.div>
        )}

        {state === "error" && (
          <motion.div
            key="error"
            layout
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="absolute inset-0 flex items-center justify-center gap-2 rounded-md border"
            style={{ borderColor: "rgba(255,69,96,0.35)", background: "rgba(255,69,96,0.08)", color: "#ff8094" }}
          >
            <XCircle size={14} />
            <span className="mono text-[10px] tracking-widest">ERROR</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Skeleton({ className }: { className?: string }) {
  return (
    <motion.div
      className={`rounded bg-white/5 ${className ?? ""}`}
      animate={{ opacity: [0.4, 0.8, 0.4] }}
      transition={{
        duration: 1.5,
        repeat: Infinity,
        repeatType: "mirror",
        ease: "easeInOut",
      }}
    />
  );
}

// ── Stock grid card ───────────────────────────────────────────────────────────
function StockCard({
  stock, selected, price, signal, changePct, spark, loading, onClick,
}: {
  stock: StockInfo; selected: boolean; price: number | null;
  signal: string | null; changePct: number | null; spark: number[];
  loading: boolean; onClick: () => void;
}) {
  const col = signal ? (SIG_COLOR[signal] ?? "#fff") : "#6a90b0";
  return (
    <button
      onClick={onClick}
      className="flex flex-col gap-1 p-3 rounded-lg text-left transition-all"
      style={{
        background: selected ? "rgba(0,255,200,0.06)" : "rgba(0,12,28,0.7)",
        border: `1px solid ${selected ? "rgba(0,255,200,0.4)" : "rgba(0,153,255,0.08)"}`,
        minWidth: 120,
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-black text-xs" style={{ fontFamily: "Orbitron, monospace", color: col }}>
          {stock.ticker}
        </span>
        {signal && (
          <span className="text-xs px-1.5 py-0.5 rounded-sm font-bold"
            style={{ background: `${col}18`, color: col, fontFamily: "Share Tech Mono, monospace", fontSize: 9 }}>
            {signal}
          </span>
        )}
      </div>
      <span className="text-xs opacity-40 truncate" style={{ fontFamily: "Share Tech Mono, monospace", maxWidth: 100 }}>
        {stock.name}
      </span>
      <div className="flex items-end justify-between gap-1 mt-1">
        <span className="text-sm font-bold" style={{ fontFamily: "Share Tech Mono, monospace", color: "#c8e0f4" }}>
          {loading ? "..." : price != null ? "$" + price.toFixed(0) : "—"}
        </span>
        {changePct != null && (
          <span className="text-xs font-bold" style={{ color: changePct >= 0 ? "#00ffcc" : "#ff4560", fontFamily: "Share Tech Mono, monospace" }}>
            {pct(changePct)}
          </span>
        )}
      </div>
      <div className="mt-1">
        <Spark values={spark} color={changePct != null && changePct >= 0 ? "#00ffcc" : "#ff4560"} />
      </div>
    </button>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [activeTicker, setActiveTicker] = useState("AAPL");
  const [data, setData] = useState<PredictionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [livePrice, setLivePrice] = useState<number | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [training, setTraining] = useState(false);
  const [trainStatus, setTrainStatus] = useState<string | null>(null);
  const [flowState, setFlowState] = useState<FlowState>("idle");
  const [flowProgress, setFlowProgress] = useState(0);
  // Mini data for the grid cards
  const [cardData, setCardData] = useState<Record<string, { price: number; signal: string; changePct: number; spark: number[] }>>({});
  const wsRef = useRef<WebSocket | null>(null);

  const fetchPrediction = useCallback(async (ticker: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/predict/${ticker}`);
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const json: PredictionResponse = await res.json();
      setData(json);
      setLivePrice(null);
      connectWs(ticker);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  const connectWs = (ticker: string) => {
    if (wsRef.current) wsRef.current.close();
    const wsUrl = API_URL.replace("http", "ws");
    const ws = new WebSocket(`${wsUrl}/ws/ticker/${ticker}`);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.price) setLivePrice(msg.price);
      } catch {}
    };
    wsRef.current = ws;
  };

  // Pre-fetch light data for all grid cards
  const fetchCardData = useCallback(async () => {
    const results: typeof cardData = {};
    await Promise.allSettled(
      STOCKS.slice(0, 8).map(async ({ ticker }) => {
        try {
          const res = await fetch(`${API_URL}/api/predict/${ticker}`);
          if (!res.ok) return;
          const d: PredictionResponse = await res.json();
          const spark = d.chart_data.slice(-20).map((x) => x.price);
          const first = spark[0] ?? d.current_price;
          results[ticker] = {
            price: d.current_price,
            signal: d.signal,
            changePct: ((d.current_price - first) / first) * 100,
            spark,
          };
        } catch {}
      })
    );
    setCardData(results);
  }, []);

  useEffect(() => {
    fetchPrediction("AAPL");
    fetchWatchlist();
    fetchCardData();
    return () => wsRef.current?.close();
  }, []);

  const handleSelectTicker = (ticker: string) => {
    setActiveTicker(ticker);
    fetchPrediction(ticker);
  };

  const fetchWatchlist = async () => {
    try {
      const res = await fetch(`${API_URL}/api/watchlist`);
      const j = await res.json();
      setWatchlist(j.watchlist ?? []);
    } catch {}
  };

  const toggleWatchlist = async (ticker: string) => {
    if (watchlist.includes(ticker)) {
      await fetch(`${API_URL}/api/watchlist/${ticker}`, { method: "DELETE" });
    } else {
      await fetch(`${API_URL}/api/watchlist/${ticker}`, { method: "POST" });
    }
    fetchWatchlist();
  };

  const trainModel = async () => {
    setTraining(true);
    setFlowState("uploading");
    setFlowProgress(6);
    setTrainStatus("Training LSTM + XGBoost...");
    const startedAt = Date.now();
    const tick = window.setInterval(() => {
      setFlowProgress((p) => Math.min(92, p + (92 - p) * 0.16 + 1));
    }, 250);
    try {
      await fetch(`${API_URL}/api/train/${activeTicker}`, { method: "POST" });
      window.clearInterval(tick);
      setFlowProgress(100);
      setFlowState("success");
      setTrainStatus("Training started in background — refresh in ~2 min");
      window.setTimeout(() => {
        fetchPrediction(activeTicker);
        setTrainStatus(null);
        setFlowState("idle");
        setFlowProgress(0);
      }, 2000);
    } catch {
      window.clearInterval(tick);
      setFlowState("error");
      setTrainStatus("Training request failed");
      window.setTimeout(() => {
        setFlowState("idle");
        setFlowProgress(0);
        setTrainStatus(null);
      }, 2500);
    } finally {
      setTraining(false);
    }
  };

  // ── Build combined chart data (history + forecast) ──
  const chartData = React.useMemo(() => {
    if (!data) return [];
    const hist = data.chart_data.map((d) => ({
      time: d.time, price: d.price, forecast: null as number | null,
      lower: null as number | null, upper: null as number | null,
    }));
    const lastPrice = hist[hist.length - 1]?.price ?? 0;
    const fore = data.forecast_data.map((d) => ({
      time: d.date, price: null as number | null,
      forecast: d.price, lower: d.lower, upper: d.upper,
    }));
    // Bridge: duplicate last historical point as first forecast point
    if (fore.length && hist.length) {
      fore.unshift({ time: hist[hist.length - 1].time, price: null, forecast: lastPrice, lower: lastPrice, upper: lastPrice });
    }
    return [...hist, ...fore];
  }, [data]);

  // ── Indicator helpers ──
  const displayPrice = livePrice ?? data?.current_price ?? 0;
  const timing = data?.timing;

  return (
    <div className="min-h-screen" style={{ background: "#030d1a", fontFamily: "Share Tech Mono, monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');
        .orb { font-family: 'Orbitron', monospace; }
        .mono { font-family: 'Share Tech Mono', monospace; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(0,255,200,0.15); border-radius: 2px; }
        .card { background: rgba(0,12,28,0.8); border: 1px solid rgba(0,153,255,0.1); border-radius: 12px; }
        .metric-card { background: rgba(0,8,20,0.9); border: 1px solid rgba(0,255,200,0.08); border-radius: 10px; transition: border-color 0.3s; }
        .metric-card:hover { border-color: rgba(0,255,200,0.25); }
        .nav-btn { background: rgba(0,255,200,0.06); border: 1px solid rgba(0,255,200,0.3); color: #00ffcc; transition: all 0.2s; }
        .nav-btn:hover { background: rgba(0,255,200,0.12); }
        .train-btn { background: rgba(0,153,255,0.08); border: 1px solid rgba(0,153,255,0.35); color: #0099ff; transition: all 0.2s; }
        .train-btn:hover { background: rgba(0,153,255,0.15); }
      `}</style>

      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-40 flex items-center justify-between px-6 py-3"
        style={{ background: "rgba(3,13,26,0.92)", backdropFilter: "blur(14px)", borderBottom: "1px solid rgba(0,255,200,0.06)" }}>
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ background: "#00ffcc", boxShadow: "0 0 8px #00ffcc" }} />
            <span className="orb text-xs font-bold tracking-widest" style={{ color: "#00ffcc" }}>STOCKSENSE AI</span>
          </Link>
          <span className="mono text-xs opacity-20" style={{ color: "#c8e0f4" }}>/ dashboard</span>
        </div>
        <div className="flex items-center gap-3">
          <ProgressFlowState state={flowState} progress={flowProgress} />
          {trainStatus && (
            <span className="mono text-xs px-3 py-1 rounded" style={{ color: "#0099ff", background: "rgba(0,153,255,0.08)", border: "1px solid rgba(0,153,255,0.2)" }}>
              {trainStatus}
            </span>
          )}
          <button onClick={trainModel} disabled={training} className="train-btn orb text-xs font-bold px-4 py-1.5 rounded tracking-widest">
            {training ? "TRAINING..." : `TRAIN ${activeTicker}`}
          </button>
          <button onClick={() => fetchPrediction(activeTicker)} className="nav-btn orb text-xs font-bold px-4 py-1.5 rounded">
            <RefreshCw size={12} className="inline mr-1.5" />REFRESH
          </button>
        </div>
      </nav>

      <div className="p-5 space-y-5">

        {/* ── Stock grid ───────────────────────────────────────────────────── */}
        <div>
          <div className="mono text-xs mb-3 tracking-widest" style={{ color: "rgba(0,255,200,0.4)" }}>
            // SELECT STOCK — {STOCKS.length} INSTRUMENTS
          </div>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {STOCKS.map((s) => {
              const cd = cardData[s.ticker];
              return (
                <StockCard
                  key={s.ticker}
                  stock={s}
                  selected={s.ticker === activeTicker}
                  price={cd?.price ?? (s.ticker === activeTicker ? displayPrice : null)}
                  signal={cd?.signal ?? (s.ticker === activeTicker ? data?.signal ?? null : null)}
                  changePct={cd?.changePct ?? (s.ticker === activeTicker && data ? data.price_change_pct : null)}
                  spark={cd?.spark ?? (s.ticker === activeTicker ? data?.chart_data.slice(-20).map((x) => x.price) ?? [] : [])}
                  loading={s.ticker === activeTicker && loading && !cd}
                  onClick={() => handleSelectTicker(s.ticker)}
                />
              );
            })}
          </div>
        </div>

        {error && (
          <div className="p-4 rounded-lg flex items-center gap-3 mono text-sm"
            style={{ background: "rgba(255,69,96,0.08)", border: "1px solid rgba(255,69,96,0.25)", color: "#ff8080" }}>
            <AlertTriangle size={16} />
            {error} — Model may not be trained yet. Click TRAIN {activeTicker} above.
          </div>
        )}

        {/* ── Hero metrics ─────────────────────────────────────────────────── */}
        {data && (
          <>
            <div className="flex items-center gap-3 flex-wrap">
              <div>
                <span className="orb text-3xl font-black" style={{ color: "#00ffcc" }}>{data.ticker}</span>
                <span className="mono text-sm ml-3 opacity-50" style={{ color: "#c8e0f4" }}>{data.name}</span>
                <span className="mono text-xs ml-2 px-2 py-0.5 rounded-sm" style={{ color: "#4a7090", background: "rgba(0,153,255,0.06)", border: "1px solid rgba(0,153,255,0.15)" }}>
                  {data.sector}
                </span>
              </div>
              <div className="ml-auto flex items-center gap-2">
                <span className="mono text-xs px-2 py-1 rounded"
                  style={{ color: TREND_COLOR[data.trend], background: `${TREND_COLOR[data.trend]}12`, border: `1px solid ${TREND_COLOR[data.trend]}30` }}>
                  {data.trend === "BULLISH" ? "▲" : data.trend === "BEARISH" ? "▼" : "→"} {data.trend}
                </span>
                <button
                  onClick={() => toggleWatchlist(data.ticker)}
                  className="mono text-xs px-3 py-1 rounded transition-colors"
                  style={{ color: watchlist.includes(data.ticker) ? "#00ffcc" : "#4a7090", border: "1px solid rgba(0,255,200,0.15)" }}>
                  {watchlist.includes(data.ticker) ? "★ Watching" : "☆ Watch"}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {[
                { label: "LIVE PRICE", value: $$(livePrice ?? data.current_price), color: "#00ffcc", live: !!livePrice },
                { label: "7D TARGET", value: $$(data.price_target_7d), sub: pct(data.price_change_pct), color: data.price_change_pct >= 0 ? "#00ffcc" : "#ff4560" },
                { label: "14D TARGET", value: $$(data.price_target_14d), color: "#0099ff" },
                { label: "30D TARGET", value: $$(data.price_target_30d), color: "#a78bfa" },
                { label: "SIGNAL", value: data.signal, color: SIG_COLOR[data.signal] },
                { label: "CONFIDENCE", value: (data.confidence * 100).toFixed(1) + "%", color: "#f5a623" },
              ].map(({ label, value, sub, color, live }) => (
                <div key={label} className="metric-card p-4">
                  <div className="mono mb-1.5 flex items-center gap-2" style={{ fontSize: 9, color: "#2a5070", letterSpacing: "0.15em" }}>
                    {label}
                    {live && <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "#00ffcc" }} />}
                  </div>
                  <div className="orb font-black text-xl" style={{ color }}>{value}</div>
                  {sub && <div className="mono text-xs mt-1" style={{ color }}>{sub}</div>}
                </div>
              ))}
            </div>

            {/* ── Main layout: chart + side panels ─────────────────────────── */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">

              {/* Chart (2/3 width) */}
              <div className="xl:col-span-2 card p-5">
                <div className="flex items-center justify-between mb-5">
                  <div>
                    <h3 className="orb text-sm font-bold" style={{ color: "#c8e0f4" }}>
                      PRICE CHART + 30-DAY FORECAST
                    </h3>
                    <p className="mono text-xs mt-1" style={{ color: "#2a5070" }}>
                      Historical prices · LSTM forecast · 95% confidence band
                    </p>
                  </div>
                  <div className="flex items-center gap-4 mono text-xs" style={{ color: "#2a5070" }}>
                    <span className="flex items-center gap-1"><span className="w-3 h-0.5 inline-block" style={{ background: "#00ffcc" }} /> Actual</span>
                    <span className="flex items-center gap-1"><span className="w-3 h-0.5 inline-block border-t border-dashed" style={{ borderColor: "#0099ff" }} /> Forecast</span>
                    <span className="flex items-center gap-1"><span className="w-3 h-2 inline-block opacity-30 rounded-sm" style={{ background: "#0099ff" }} /> 95% CI</span>
                  </div>
                </div>

                <div style={{ height: 380 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData} margin={{ left: 0, right: 0 }}>
                      <defs>
                        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#00ffcc" stopOpacity={0.18} />
                          <stop offset="95%" stopColor="#00ffcc" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="foreGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#0099ff" stopOpacity={0.18} />
                          <stop offset="95%" stopColor="#0099ff" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,255,200,0.04)" vertical={false} />
                      <XAxis dataKey="time" stroke="#1a3a5c" fontSize={10} tickLine={false} axisLine={false}
                        interval={Math.floor(chartData.length / 8)} tick={{ fontFamily: "Share Tech Mono" }} />
                      <YAxis stroke="#1a3a5c" fontSize={10} tickLine={false} axisLine={false}
                        domain={["auto", "auto"]} tickFormatter={(v) => "$" + v.toFixed(0)}
                        tick={{ fontFamily: "Share Tech Mono" }} width={55} />
                      <Tooltip
                        contentStyle={{ background: "#010816", border: "1px solid rgba(0,255,200,0.15)", borderRadius: 8, fontFamily: "Share Tech Mono" }}
                        itemStyle={{ color: "#00ffcc" }}
                        labelStyle={{ color: "#4a7090", fontSize: 11 }}
                        formatter={(val: number, name: string) => {
                          if (name === "price")    return ["$" + val?.toFixed(2), "Price"];
                          if (name === "forecast") return ["$" + val?.toFixed(2), "Forecast"];
                          if (name === "upper")    return ["$" + val?.toFixed(2), "Upper CI"];
                          if (name === "lower")    return ["$" + val?.toFixed(2), "Lower CI"];
                          return [val, name];
                        }}
                      />
                      {/* Confidence interval area */}
                      <Area dataKey="upper" stroke="none" fill="#0099ff" fillOpacity={0.06} connectNulls />
                      <Area dataKey="lower" stroke="none" fill="#030d1a" fillOpacity={1} connectNulls />
                      {/* Historical price */}
                      <Area dataKey="price" stroke="#00ffcc" strokeWidth={2}
                        fill="url(#areaGrad)" fillOpacity={1} dot={false} connectNulls />
                      {/* Forecast line */}
                      <Line dataKey="forecast" stroke="#0099ff" strokeWidth={2}
                        strokeDasharray="5 3" dot={false} connectNulls />
                      {/* Today reference */}
                      <ReferenceLine
                        x={data.chart_data[data.chart_data.length - 1]?.time}
                        stroke="rgba(0,255,200,0.2)" strokeDasharray="3 3" label={{ value: "TODAY", fill: "#2a5070", fontSize: 9, fontFamily: "Share Tech Mono" }}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Right column: timing + technicals */}
              <div className="space-y-4">

                {/* Timing analysis */}
                {timing && (
                  <div className="card p-5">
                    <div className="mono text-xs mb-4 tracking-widest" style={{ color: "rgba(0,255,200,0.4)" }}>
                      // TIMING ANALYSIS
                    </div>
                    <div className="flex gap-4 items-start">
                      <TimingGauge score={timing.timing_score} />
                      <div className="flex-1 space-y-2">
                        <div>
                          <div className="mono text-xs mb-1" style={{ color: "#2a5070", fontSize: 9, letterSpacing: "0.15em" }}>ACTION</div>
                          <span className="orb text-xs font-black px-2 py-1 rounded"
                            style={{ color: ACTION_COLOR[timing.action], background: `${ACTION_COLOR[timing.action]}12`, border: `1px solid ${ACTION_COLOR[timing.action]}30` }}>
                            {timing.action.replace(/_/g, " ")}
                          </span>
                        </div>
                        <div>
                          <div className="mono text-xs mb-1" style={{ color: "#2a5070", fontSize: 9, letterSpacing: "0.15em" }}>RISK</div>
                          <span className="orb text-xs font-black px-2 py-1 rounded"
                            style={{ color: RISK_COLOR[timing.risk_level], background: `${RISK_COLOR[timing.risk_level]}12`, border: `1px solid ${RISK_COLOR[timing.risk_level]}30` }}>
                            {timing.risk_level}
                          </span>
                        </div>
                        {timing.days_to_opportunity != null && (
                          <div className="mono text-xs" style={{ color: "#0099ff" }}>
                            ~{timing.days_to_opportunity}d to opportunity
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="mt-4 space-y-2">
                      {[
                        { label: "BUY ZONE", value: `${$$(timing.buy_zone_low)} – ${$$(timing.buy_zone_high)}`, color: "#00ffcc" },
                        { label: "STOP LOSS", value: $$(timing.stop_loss), color: "#ff4560" },
                      ].map(({ label, value, color }) => (
                        <div key={label} className="flex justify-between items-center py-1.5 px-3 rounded"
                          style={{ background: `${color}06`, border: `1px solid ${color}18` }}>
                          <span className="mono text-xs" style={{ color: "#2a5070", fontSize: 9, letterSpacing: "0.15em" }}>{label}</span>
                          <span className="orb text-xs font-bold" style={{ color }}>{value}</span>
                        </div>
                      ))}
                    </div>

                    {timing.rationale.length > 0 && (
                      <div className="mt-4">
                        <div className="mono text-xs mb-2" style={{ color: "#2a5070", fontSize: 9, letterSpacing: "0.15em" }}>SIGNALS</div>
                        <ul className="space-y-1.5">
                          {timing.rationale.map((r, i) => (
                            <li key={i} className="flex gap-2 items-start mono text-xs" style={{ color: "#3a6080", lineHeight: 1.5 }}>
                              <ChevronRight size={10} className="mt-0.5 shrink-0" style={{ color: "#00ffcc" }} />
                              {r}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {/* Technical indicators */}
                {data && (
                  <div className="card p-5">
                    <div className="mono text-xs mb-4 tracking-widest" style={{ color: "rgba(0,255,200,0.4)" }}>
                      // TECHNICAL INDICATORS
                    </div>
                    <div className="space-y-3">
                      {[
                        {
                          label: "RSI (14)",
                          value: data.rsi?.toFixed(1) ?? "—",
                          status: data.rsi != null ? (data.rsi > 70 ? "Overbought" : data.rsi < 30 ? "Oversold" : "Neutral") : "—",
                          color: data.rsi != null ? (data.rsi > 70 ? "#ff4560" : data.rsi < 30 ? "#00ffcc" : "#f5a623") : "#4a7090",
                          bar: data.rsi,
                          barMax: 100,
                        },
                        {
                          label: "MACD",
                          value: data.macd != null ? (data.macd >= 0 ? "+" : "") + data.macd.toFixed(2) : "—",
                          status: data.macd != null ? (data.macd > 0 ? "Bullish" : "Bearish") : "—",
                          color: data.macd != null ? (data.macd > 0 ? "#00ffcc" : "#ff4560") : "#4a7090",
                          bar: null,
                          barMax: 100,
                        },
                        {
                          label: "Sentiment",
                          value: data.sentiment_score.toFixed(2),
                          status: data.sentiment_score > 0.6 ? "Bullish" : data.sentiment_score < 0.4 ? "Bearish" : "Neutral",
                          color: data.sentiment_score > 0.6 ? "#00ffcc" : data.sentiment_score < 0.4 ? "#ff4560" : "#f5a623",
                          bar: data.sentiment_score * 100,
                          barMax: 100,
                        },
                        {
                          label: "BB Upper",
                          value: data.bollinger_upper?.toFixed(2) ?? "—",
                          status: data.current_price > (data.bollinger_upper ?? Infinity) ? "Above Band" : "Below Band",
                          color: "#a78bfa",
                          bar: null,
                          barMax: 100,
                        },
                        {
                          label: "BB Lower",
                          value: data.bollinger_lower?.toFixed(2) ?? "—",
                          status: data.current_price < (data.bollinger_lower ?? 0) ? "Below Band" : "Above Band",
                          color: "#0099ff",
                          bar: null,
                          barMax: 100,
                        },
                        {
                          label: "SMA 20",
                          value: data.sma_20?.toFixed(2) ?? "—",
                          status: data.sma_20 != null ? (data.current_price > data.sma_20 ? "Above" : "Below") : "—",
                          color: data.sma_20 != null ? (data.current_price > data.sma_20 ? "#00ffcc" : "#ff4560") : "#4a7090",
                          bar: null,
                          barMax: 100,
                        },
                      ].map(({ label, value, status, color, bar, barMax }) => (
                        <div key={label}>
                          <div className="flex justify-between items-center mb-1">
                            <div>
                              <span className="mono text-xs" style={{ color: "#c8e0f4" }}>{label}</span>
                              <span className="mono text-xs ml-2" style={{ color: "#2a5070", fontSize: 9 }}>{status}</span>
                            </div>
                            <span className="orb text-xs font-bold" style={{ color }}>{value}</span>
                          </div>
                          {bar != null && (
                            <div className="h-0.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}>
                              <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.min(100, (bar / barMax) * 100)}%`, background: color }} />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* ── Price targets row ─────────────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { label: "7-DAY PRICE TARGET", value: data.price_target_7d, current: data.current_price, col: "#00ffcc" },
                { label: "14-DAY PRICE TARGET", value: data.price_target_14d, current: data.current_price, col: "#0099ff" },
                { label: "30-DAY PRICE TARGET", value: data.price_target_30d, current: data.current_price, col: "#a78bfa" },
              ].map(({ label, value, current, col }) => {
                const change = ((value - current) / current) * 100;
                const isUp = change >= 0;
                return (
                  <div key={label} className="card p-5 flex items-center justify-between">
                    <div>
                      <div className="mono mb-2" style={{ fontSize: 9, color: "#2a5070", letterSpacing: "0.15em" }}>{label}</div>
                      <div className="orb text-2xl font-black" style={{ color: col }}>{$$(value)}</div>
                      <div className="mono text-xs mt-1 flex items-center gap-1" style={{ color: isUp ? "#00ffcc" : "#ff4560" }}>
                        {isUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                        {pct(change)} vs current
                      </div>
                    </div>
                    <div className="w-16 h-16 rounded-full flex items-center justify-center"
                      style={{ background: `${col}08`, border: `1px solid ${col}20` }}>
                      {isUp ? <TrendingUp size={24} style={{ color: col }} /> : <TrendingDown size={24} style={{ color: col }} />}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}

        {loading && !data && (
          <div className="space-y-5 py-2">
            <div className="card p-5">
              <Skeleton className="h-6 w-40 mb-2" />
              <Skeleton className="h-3 w-72 mb-1.5" />
              <Skeleton className="h-3 w-56" />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={`metric-skeleton-${i}`} className="metric-card p-4">
                  <Skeleton className="h-3 w-20 mb-3" />
                  <Skeleton className="h-7 w-16 mb-2" />
                  <Skeleton className="h-3 w-12" />
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
              <div className="xl:col-span-2 card p-5">
                <Skeleton className="h-5 w-56 mb-2" />
                <Skeleton className="h-3 w-80 mb-5" />
                <Skeleton className="h-[380px] w-full" />
              </div>

              <div className="space-y-4">
                <div className="card p-5">
                  <Skeleton className="h-4 w-40 mb-4" />
                  <Skeleton className="h-24 w-full mb-3" />
                  <Skeleton className="h-3 w-full mb-2" />
                  <Skeleton className="h-3 w-3/4 mb-2" />
                  <Skeleton className="h-3 w-4/5" />
                </div>
                <div className="card p-5">
                  <Skeleton className="h-4 w-44 mb-4" />
                  <Skeleton className="h-3 w-full mb-2" />
                  <Skeleton className="h-3 w-5/6 mb-2" />
                  <Skeleton className="h-3 w-2/3" />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={`target-skeleton-${i}`} className="card p-5">
                  <Skeleton className="h-3 w-36 mb-3" />
                  <Skeleton className="h-8 w-28 mb-2" />
                  <Skeleton className="h-3 w-24" />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
