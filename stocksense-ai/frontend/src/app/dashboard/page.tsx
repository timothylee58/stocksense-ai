"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ComposedChart, Line,
} from "recharts";
import { AnimatePresence, motion } from "framer-motion";
import { TrendingUp, TrendingDown, AlertTriangle, ChevronRight, Upload, CheckCircle2, XCircle, RefreshCw } from "lucide-react";
import Link from "next/link";
import { PredictionResponse, StockInfo } from "@/types/stock";
import StockBriefingPanel from "@/components/StockBriefingPanel";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Mercury palette ──────────────────────────────────────────────────────────
const C = {
  bg: "#F6F4EF",
  panel: "#FFFFFF",
  panelAlt: "#FBFAF6",
  line: "#E6E2D9",
  lineStrong: "#D8D3C8",
  ink: "#17191E",
  inkSoft: "#3C3E44",
  muted: "#6E7075",
  faint: "#9C978D",
  accent: "#1F5E46",
  accentSoft: "#E9F1EC",
  danger: "#A33A31",
  dangerSoft: "#F9EBE8",
  warn: "#8A6430",
  warnSoft: "#F7EFE1",
  info: "#4251A8",
  infoSoft: "#ECEEF9",
  plum: "#6B5CA5",
  track: "#EFEDE7",
};

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
  BUY: C.accent, SELL: C.danger, HOLD: C.warn,
};
const TREND_COLOR: Record<string, string> = {
  BULLISH: C.accent, BEARISH: C.danger, SIDEWAYS: C.warn,
};
const ACTION_COLOR: Record<string, string> = {
  BUY_NOW: C.accent, WAIT_FOR_DIP: C.info, HOLD: C.warn,
  SELL_NOW: C.danger, AVOID: C.danger,
};
const RISK_COLOR: Record<string, string> = {
  LOW: C.accent, MEDIUM: C.warn, HIGH: C.danger,
};

const EASE = [0.22, 1, 0.36, 1] as const;

function pct(v: number) { return (v >= 0 ? "+" : "") + v.toFixed(2) + "%"; }
function $$(v: number | null | undefined) { return v != null ? "$" + v.toFixed(2) : "—"; }
function score10Color(s: number) {
  if (s >= 7) return C.accent;
  if (s >= 5) return C.warn;
  return C.danger;
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
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth={1.4} strokeLinecap="round" />
    </svg>
  );
}

// ── Timing score gauge ────────────────────────────────────────────────────────
function TimingGauge({ score }: { score: number }) {
  const col = score10Color(score);
  const pct = (score / 10) * 100;
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-28 w-28">
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
          <circle cx="50" cy="50" r="42" fill="none" stroke={C.track} strokeWidth="8" />
          <circle
            cx="50" cy="50" r="42"
            fill="none"
            stroke={col}
            strokeWidth="8"
            strokeDasharray={`${2 * Math.PI * 42 * pct / 100} ${2 * Math.PI * 42 * (1 - pct / 100)}`}
            strokeLinecap="round"
            style={{ transition: "stroke-dasharray 0.8s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="serif text-[26px] font-semibold leading-none" style={{ color: C.ink }}>
            {score.toFixed(1)}
          </span>
          <span className="mono text-[9px]" style={{ color: C.faint }}>/10</span>
        </div>
      </div>
      <span className="mono text-[9px] uppercase tracking-[0.16em]" style={{ color: C.faint }}>
        Timing score
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
    <div className="relative h-9 w-40">
      <AnimatePresence mode="wait">
        {state === "idle" && (
          <motion.div
            key="idle"
            layout
            initial={{ opacity: 0, scale: 0.94 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.94 }}
            className="absolute inset-0 flex items-center justify-center gap-2 rounded-full border"
            style={{ borderColor: C.line, background: C.panel, color: C.muted }}
          >
            <Upload size={12} />
            <span className="mono text-[9px] uppercase tracking-[0.12em]">Idle</span>
          </motion.div>
        )}

        {state === "uploading" && (
          <motion.div
            key="uploading"
            layout
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="absolute inset-0 rounded-full border px-3 py-1.5"
            style={{ borderColor: C.line, background: C.infoSoft }}
          >
            <div className="mono flex items-center justify-between text-[9px] uppercase tracking-[0.10em]" style={{ color: C.info }}>
              <span>Training</span>
              <span>{Math.round(progress)}%</span>
            </div>
            <div className="mt-1 h-0.5 w-full rounded-full" style={{ background: C.line }}>
              <motion.div
                animate={{ width: `${progress}%` }}
                transition={{ ease: "easeOut" }}
                className="h-0.5 rounded-full"
                style={{ background: C.info }}
              />
            </div>
          </motion.div>
        )}

        {state === "success" && (
          <motion.div
            key="success"
            layout
            initial={{ scale: 0.84, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ opacity: 0, scale: 0.94 }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
            className="absolute inset-0 flex items-center justify-center gap-2 rounded-full border"
            style={{ borderColor: C.accent, background: C.accentSoft, color: C.accent }}
          >
            <CheckCircle2 size={12} />
            <span className="mono text-[9px] uppercase tracking-[0.12em]">Started</span>
          </motion.div>
        )}

        {state === "error" && (
          <motion.div
            key="error"
            layout
            initial={{ opacity: 0, scale: 0.94 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.94 }}
            className="absolute inset-0 flex items-center justify-center gap-2 rounded-full border"
            style={{ borderColor: C.danger, background: C.dangerSoft, color: C.danger }}
          >
            <XCircle size={12} />
            <span className="mono text-[9px] uppercase tracking-[0.12em]">Failed</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Skeleton({ className }: { className?: string }) {
  return (
    <motion.div
      className={`rounded ${className ?? ""}`}
      style={{ background: "rgba(23,25,30,0.06)" }}
      animate={{ opacity: [0.35, 0.7, 0.35] }}
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
  const col = signal ? (SIG_COLOR[signal] ?? C.ink) : C.muted;
  return (
    <button
      onClick={onClick}
      className="flex min-w-[128px] flex-col gap-1 rounded-xl p-3.5 text-left transition-all hover:-translate-y-0.5"
      style={{
        background: selected ? C.accentSoft : C.panel,
        border: `1px solid ${selected ? C.accent : C.line}`,
        boxShadow: selected ? "0 8px 20px rgba(31,94,70,0.08)" : "0 1px 2px rgba(23,25,30,0.03)",
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="serif text-[13px] font-semibold" style={{ color: selected ? C.accent : C.ink }}>
          {stock.ticker}
        </span>
        {signal && (
          <span
            className="mono rounded-full px-1.5 py-0.5 text-[8px] uppercase tracking-[0.08em]"
            style={{ background: `${col}14`, color: col, border: `1px solid ${col}2E` }}
          >
            {signal}
          </span>
        )}
      </div>
      <span className="truncate text-[10px]" style={{ color: C.faint, maxWidth: 104 }}>
        {stock.name}
      </span>
      <div className="mt-1 flex items-end justify-between gap-1">
        <span className="mono text-[13px] font-bold" style={{ color: C.ink }}>
          {loading ? "…" : price != null ? "$" + price.toFixed(0) : "—"}
        </span>
        {changePct != null && (
          <span className="mono text-[10px] font-bold" style={{ color: changePct >= 0 ? C.accent : C.danger }}>
            {pct(changePct)}
          </span>
        )}
      </div>
      <div className="mt-1">
        <Spark values={spark} color={changePct != null && changePct >= 0 ? C.accent : C.danger} />
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
      STOCKS.slice(0, 10).map(async ({ ticker }) => {
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
    <div className="min-h-screen" style={{ background: C.bg, color: C.ink }}>
      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <nav
        className="sticky top-0 z-40 flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 md:px-8"
        style={{ background: "rgba(246,244,239,0.90)", backdropFilter: "blur(16px)", borderBottom: `1px solid ${C.line}` }}
      >
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/" className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: C.accent }} />
            <span className="serif text-[15px] font-semibold">StockSense</span>
            <span className="mono text-[8px] uppercase tracking-[0.2em]" style={{ color: C.faint }}>AI</span>
          </Link>
          <span className="mono hidden text-[10px] sm:inline" style={{ color: C.lineStrong }}>/</span>
          <span className="mono hidden text-[10px] uppercase tracking-[0.12em] sm:inline" style={{ color: C.muted }}>Dashboard</span>
          <div className="no-scrollbar ml-1 flex max-w-full flex-nowrap items-center gap-1.5 overflow-x-auto">
            <Link href="/dashboard/sentiment" className="pill transition-colors hover:border-[#D8D3C8]">
              Sentiment
            </Link>
            <Link href="/dashboard/anomalies" className="pill transition-colors hover:border-[#D8D3C8]">
              Anomalies
            </Link>
            <Link
              href="/dashboard/bursa"
              className="pill"
              style={{ color: C.warn, background: C.warnSoft, borderColor: "#E7D9BE" }}
            >
              Bursa &amp; Sens
            </Link>
            <Link
              href="/dashboard/ops"
              className="pill"
              style={{ color: C.accent, background: C.accentSoft, borderColor: "#CFE0D5" }}
            >
              Ops
            </Link>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="hidden sm:block">
            <ProgressFlowState state={flowState} progress={flowProgress} />
          </div>
          {trainStatus && (
            <span className="mono rounded-full px-3 py-1 text-[9px] uppercase tracking-[0.08em]"
              style={{ color: C.info, background: C.infoSoft, border: `1px solid ${C.line}` }}>
              {trainStatus}
            </span>
          )}
          <button
            onClick={trainModel}
            disabled={training}
            className="mono rounded-full px-4 py-1.5 text-[10px] uppercase tracking-[0.1em] transition-opacity disabled:opacity-50"
            style={{ background: C.ink, color: C.bg }}
          >
            {training ? "Training…" : `Train ${activeTicker}`}
          </button>
          <button
            onClick={() => fetchPrediction(activeTicker)}
            className="mono flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-[10px] uppercase tracking-[0.1em] transition-colors hover:bg-white"
            style={{ borderColor: C.lineStrong, color: C.inkSoft, background: C.panel }}
          >
            <RefreshCw size={11} /> Refresh
          </button>
        </div>
      </nav>

      <div className="mx-auto max-w-[1500px] space-y-5 p-5 md:p-7">

        {/* ── Intro + stock grid ───────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE }}
        >
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="eyebrow mb-2">Paper account · SIMULATE</div>
              <h1 className="serif text-[28px] font-semibold leading-none md:text-[32px]">Market overview</h1>
            </div>
            <span className="mono text-[10px] uppercase tracking-[0.12em]" style={{ color: C.faint }}>
              {STOCKS.length} instruments
            </span>
          </div>
          <div className="no-scrollbar flex gap-2.5 overflow-x-auto pb-2">
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
        </motion.div>

        {error && (
          <div className="flex items-center gap-3 rounded-xl px-4 py-3 text-[13px]"
            style={{ background: C.dangerSoft, border: `1px solid #EBD2CD`, color: C.danger }}>
            <AlertTriangle size={15} />
            {error} — Model may not be trained yet. Click Train {activeTicker} above.
          </div>
        )}

        {/* ── Hero metrics ─────────────────────────────────────────────────── */}
        {data && (
          <>
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55 }}
              className="flex flex-wrap items-center gap-3"
            >
              <div className="flex flex-wrap items-baseline gap-3">
                <span className="serif text-[32px] font-semibold leading-none">{data.ticker}</span>
                {data.name && data.name.toUpperCase() !== data.ticker && (
                  <span className="text-[14px]" style={{ color: C.muted }}>{data.name}</span>
                )}
                {data.sector && data.sector.toUpperCase() !== "UNKNOWN" && (
                  <span className="pill">{data.sector}</span>
                )}
              </div>
              <div className="ml-auto flex items-center gap-2">
                <span
                  className="pill"
                  style={{
                    color: TREND_COLOR[data.trend],
                    background: `${TREND_COLOR[data.trend]}0F`,
                    borderColor: `${TREND_COLOR[data.trend]}30`,
                  }}
                >
                  {data.trend === "BULLISH" ? "▲" : data.trend === "BEARISH" ? "▼" : "→"} {data.trend}
                </span>
                <button
                  onClick={() => toggleWatchlist(data.ticker)}
                  className="mono rounded-full border px-3.5 py-1.5 text-[10px] uppercase tracking-[0.08em] transition-colors hover:bg-white"
                  style={{
                    color: watchlist.includes(data.ticker) ? C.accent : C.muted,
                    borderColor: watchlist.includes(data.ticker) ? C.accent : C.line,
                    background: watchlist.includes(data.ticker) ? C.accentSoft : C.panel,
                  }}
                >
                  {watchlist.includes(data.ticker) ? "★ Watching" : "☆ Watch"}
                </button>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.06 }}
              className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6"
            >
              {[
                { label: "Live price", value: $$(livePrice ?? data.current_price), color: C.ink, live: !!livePrice },
                { label: "7d target", value: $$(data.price_target_7d), sub: pct(data.price_change_pct), color: C.ink },
                { label: "14d target", value: $$(data.price_target_14d), color: C.ink },
                { label: "30d target", value: $$(data.price_target_30d), color: C.ink },
                { label: "Signal", value: data.signal, color: SIG_COLOR[data.signal] },
                { label: "Confidence", value: (data.confidence * 100).toFixed(1) + "%", color: C.ink },
              ].map(({ label, value, sub, color, live }) => (
                <div key={label} className="metric-card p-4">
                  <div className="mono mb-2 flex items-center gap-2 text-[9px] uppercase tracking-[0.14em]" style={{ color: C.faint }}>
                    {label}
                    {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full" style={{ background: C.accent }} />}
                  </div>
                  <div className="mono text-[18px] font-bold leading-none" style={{ color, fontVariantNumeric: "tabular-nums" }}>
                    {value}
                  </div>
                  {sub && <div className="mono mt-1.5 text-[10px]" style={{ color: data.price_change_pct >= 0 ? C.accent : C.danger }}>{sub}</div>}
                </div>
              ))}
            </motion.div>

            {/* ── Main layout: chart + side panels ─────────────────────────── */}
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">

              {/* Chart (2/3 width) */}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.12 }}
                className="card flex flex-col p-5 xl:col-span-2"
              >
                <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <h3 className="serif text-[17px] font-semibold">Price &amp; 30-day forecast</h3>
                    <p className="mt-1 text-[12px]" style={{ color: C.muted }}>
                      Historical closes · LSTM forecast · 95% confidence band
                    </p>
                  </div>
                  <div className="mono flex items-center gap-4 text-[9px] uppercase tracking-[0.08em]" style={{ color: C.muted }}>
                    <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4" style={{ background: C.accent }} /> Actual</span>
                    <span className="flex items-center gap-1.5"><span className="inline-block w-4 border-t border-dashed" style={{ borderColor: C.info }} /> Forecast</span>
                    <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-4 rounded-sm" style={{ background: C.infoSoft, border: `1px solid ${C.line}` }} /> 95% CI</span>
                  </div>
                </div>

                <div className="flex-1" style={{ minHeight: 380 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData} margin={{ left: 0, right: 0 }}>
                      <defs>
                        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={C.accent} stopOpacity={0.16} />
                          <stop offset="95%" stopColor={C.accent} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="2 4" stroke={C.track} vertical={false} />
                      <XAxis dataKey="time" stroke={C.faint} fontSize={10} tickLine={false} axisLine={false}
                        interval={Math.floor(chartData.length / 8)} tick={{ fontFamily: "Space Mono" }} />
                      <YAxis stroke={C.faint} fontSize={10} tickLine={false} axisLine={false}
                        domain={["auto", "auto"]} tickFormatter={(v) => "$" + v.toFixed(0)}
                        tick={{ fontFamily: "Space Mono" }} width={55} />
                      <Tooltip
                        contentStyle={{ background: C.panel, border: `1px solid ${C.line}`, borderRadius: 12, fontFamily: "Space Mono", fontSize: 11, boxShadow: "0 12px 30px rgba(23,25,30,0.08)" }}
                        itemStyle={{ color: C.ink }}
                        labelStyle={{ color: C.faint, fontSize: 10 }}
                        formatter={(val, name) => {
                          const v = typeof val === "number" ? val.toFixed(2) : String(val ?? "");
                          if (name === "price")    return ["$" + v, "Price"];
                          if (name === "forecast") return ["$" + v, "Forecast"];
                          if (name === "upper")    return ["$" + v, "Upper CI"];
                          if (name === "lower")    return ["$" + v, "Lower CI"];
                          return [v, String(name ?? "")];
                        }}
                      />
                      {/* Confidence interval area */}
                      <Area dataKey="upper" stroke="none" fill={C.info} fillOpacity={0.08} connectNulls />
                      <Area dataKey="lower" stroke="none" fill={C.panel} fillOpacity={1} connectNulls />
                      {/* Historical price */}
                      <Area dataKey="price" stroke={C.accent} strokeWidth={1.8}
                        fill="url(#areaGrad)" fillOpacity={1} dot={false} connectNulls />
                      {/* Forecast line */}
                      <Line dataKey="forecast" stroke={C.info} strokeWidth={1.8}
                        strokeDasharray="5 4" dot={false} connectNulls />
                      {/* Today reference */}
                      <ReferenceLine
                        x={data.chart_data[data.chart_data.length - 1]?.time}
                        stroke={C.lineStrong} strokeDasharray="3 3"
                        label={{ value: "TODAY", fill: C.faint, fontSize: 9, fontFamily: "Space Mono" }}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>

              {/* Right column: timing + technicals */}
              <div className="space-y-5">

                {/* Timing analysis */}
                {timing && (
                  <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.18 }}
                    className="card p-5"
                  >
                    <div className="eyebrow mb-4">Timing analysis</div>
                    <div className="flex items-start gap-5">
                      <TimingGauge score={timing.timing_score} />
                      <div className="flex-1 space-y-3">
                        <div>
                          <div className="mono mb-1.5 text-[9px] uppercase tracking-[0.14em]" style={{ color: C.faint }}>Action</div>
                          <span
                            className="mono inline-flex rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.06em]"
                            style={{
                              color: ACTION_COLOR[timing.action],
                              background: `${ACTION_COLOR[timing.action]}0F`,
                              borderColor: `${ACTION_COLOR[timing.action]}30`,
                            }}
                          >
                            {timing.action.replace(/_/g, " ")}
                          </span>
                        </div>
                        <div>
                          <div className="mono mb-1.5 text-[9px] uppercase tracking-[0.14em]" style={{ color: C.faint }}>Risk</div>
                          <span
                            className="mono inline-flex rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.06em]"
                            style={{
                              color: RISK_COLOR[timing.risk_level],
                              background: `${RISK_COLOR[timing.risk_level]}0F`,
                              borderColor: `${RISK_COLOR[timing.risk_level]}30`,
                            }}
                          >
                            {timing.risk_level}
                          </span>
                        </div>
                        {timing.days_to_opportunity != null && (
                          <div className="mono text-[10px]" style={{ color: C.info }}>
                            ~{timing.days_to_opportunity}d to opportunity
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="mt-5 space-y-2">
                      {[
                        { label: "Buy zone", value: `${$$(timing.buy_zone_low)} – ${$$(timing.buy_zone_high)}`, color: C.accent, bg: C.accentSoft },
                        { label: "Stop loss", value: $$(timing.stop_loss), color: C.danger, bg: C.dangerSoft },
                      ].map(({ label, value, color, bg }) => (
                        <div key={label} className="flex items-center justify-between rounded-lg px-3 py-2"
                          style={{ background: bg, border: `1px solid ${C.line}` }}>
                          <span className="mono text-[9px] uppercase tracking-[0.14em]" style={{ color: C.muted }}>{label}</span>
                          <span className="mono text-[11px] font-bold" style={{ color }}>{value}</span>
                        </div>
                      ))}
                    </div>

                    {timing.rationale.length > 0 && (
                      <div className="mt-5">
                        <div className="mono mb-2 text-[9px] uppercase tracking-[0.14em]" style={{ color: C.faint }}>Signals</div>
                        <ul className="space-y-1.5">
                          {timing.rationale.map((r, i) => (
                            <li key={i} className="flex items-start gap-2 text-[12px] leading-snug" style={{ color: C.inkSoft }}>
                              <ChevronRight size={11} className="mt-0.5 shrink-0" style={{ color: C.accent }} />
                              {r}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </motion.div>
                )}

                {/* Technical indicators */}
                {data && (
                  <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.24 }}
                    className="card p-5"
                  >
                    <div className="eyebrow mb-4">Technical indicators</div>
                    <div className="space-y-3.5">
                      {[
                        {
                          label: "RSI (14)",
                          value: data.rsi?.toFixed(1) ?? "—",
                          status: data.rsi != null ? (data.rsi > 70 ? "Overbought" : data.rsi < 30 ? "Oversold" : "Neutral") : "—",
                          color: data.rsi != null ? (data.rsi > 70 ? C.danger : data.rsi < 30 ? C.accent : C.warn) : C.faint,
                          bar: data.rsi,
                          barMax: 100,
                        },
                        {
                          label: "MACD",
                          value: data.macd != null ? (data.macd >= 0 ? "+" : "") + data.macd.toFixed(2) : "—",
                          status: data.macd != null ? (data.macd > 0 ? "Bullish" : "Bearish") : "—",
                          color: data.macd != null ? (data.macd > 0 ? C.accent : C.danger) : C.faint,
                          bar: null,
                          barMax: 100,
                        },
                        {
                          label: "Sentiment",
                          value: data.sentiment_score.toFixed(2),
                          status: data.sentiment_score > 0.6 ? "Bullish" : data.sentiment_score < 0.4 ? "Bearish" : "Neutral",
                          color: data.sentiment_score > 0.6 ? C.accent : data.sentiment_score < 0.4 ? C.danger : C.warn,
                          bar: data.sentiment_score * 100,
                          barMax: 100,
                        },
                        {
                          label: "BB upper",
                          value: data.bollinger_upper?.toFixed(2) ?? "—",
                          status: data.current_price > (data.bollinger_upper ?? Infinity) ? "Above band" : "Below band",
                          color: C.plum,
                          bar: null,
                          barMax: 100,
                        },
                        {
                          label: "BB lower",
                          value: data.bollinger_lower?.toFixed(2) ?? "—",
                          status: data.current_price < (data.bollinger_lower ?? 0) ? "Below band" : "Above band",
                          color: C.info,
                          bar: null,
                          barMax: 100,
                        },
                        {
                          label: "SMA 20",
                          value: data.sma_20?.toFixed(2) ?? "—",
                          status: data.sma_20 != null ? (data.current_price > data.sma_20 ? "Above" : "Below") : "—",
                          color: data.sma_20 != null ? (data.current_price > data.sma_20 ? C.accent : C.danger) : C.faint,
                          bar: null,
                          barMax: 100,
                        },
                      ].map(({ label, value, status, color, bar, barMax }) => (
                        <div key={label}>
                          <div className="mb-1.5 flex items-center justify-between">
                            <div className="flex items-baseline gap-2">
                              <span className="mono text-[11px]" style={{ color: C.inkSoft }}>{label}</span>
                              <span className="mono text-[9px] uppercase tracking-[0.06em]" style={{ color: C.faint }}>{status}</span>
                            </div>
                            <span className="mono text-[11px] font-bold" style={{ color }}>{value}</span>
                          </div>
                          {bar != null && (
                            <div className="h-1 overflow-hidden rounded-full" style={{ background: C.track }}>
                              <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.min(100, (bar / barMax) * 100)}%`, background: color }} />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </div>
            </div>

            {/* ── Price targets row ─────────────────────────────────────────── */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="grid grid-cols-1 gap-4 md:grid-cols-3"
            >
              {[
                { label: "7-day price target", value: data.price_target_7d, current: data.current_price, col: C.accent },
                { label: "14-day price target", value: data.price_target_14d, current: data.current_price, col: C.info },
                { label: "30-day price target", value: data.price_target_30d, current: data.current_price, col: C.plum },
              ].map(({ label, value, current, col }) => {
                const change = ((value - current) / current) * 100;
                const isUp = change >= 0;
                return (
                  <div key={label} className="card flex items-center justify-between p-5">
                    <div>
                      <div className="mono mb-2 text-[9px] uppercase tracking-[0.14em]" style={{ color: C.faint }}>{label}</div>
                      <div className="mono text-[24px] font-bold leading-none" style={{ color: C.ink }}>{$$(value)}</div>
                      <div className="mono mt-2 flex items-center gap-1 text-[10px]" style={{ color: isUp ? C.accent : C.danger }}>
                        {isUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                        {pct(change)} vs current
                      </div>
                    </div>
                    <div className="flex h-12 w-12 items-center justify-center rounded-full"
                      style={{ background: `${col}0D`, border: `1px solid ${C.line}` }}>
                      {isUp ? <TrendingUp size={18} style={{ color: col }} /> : <TrendingDown size={18} style={{ color: col }} />}
                    </div>
                  </div>
                );
              })}
            </motion.div>

            {/* ── AI Stock Briefing ────────────────────────────────────────── */}
            <StockBriefingPanel ticker={activeTicker} />
          </>
        )}

        {loading && !data && (
          <div className="space-y-5 py-2">
            <div className="card p-5">
              <Skeleton className="mb-2 h-6 w-40" />
              <Skeleton className="mb-2 h-3 w-72" />
              <Skeleton className="h-3 w-56" />
            </div>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={`metric-skeleton-${i}`} className="metric-card p-4">
                  <Skeleton className="mb-3 h-3 w-20" />
                  <Skeleton className="mb-2 h-7 w-16" />
                  <Skeleton className="h-3 w-12" />
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
              <div className="card p-5 xl:col-span-2">
                <Skeleton className="mb-2 h-5 w-56" />
                <Skeleton className="mb-5 h-3 w-80" />
                <Skeleton className="h-[380px] w-full" />
              </div>

              <div className="space-y-5">
                <div className="card p-5">
                  <Skeleton className="mb-4 h-4 w-40" />
                  <Skeleton className="mb-3 h-24 w-full" />
                  <Skeleton className="mb-2 h-3 w-full" />
                  <Skeleton className="mb-2 h-3 w-3/4" />
                  <Skeleton className="h-3 w-4/5" />
                </div>
                <div className="card p-5">
                  <Skeleton className="mb-4 h-4 w-44" />
                  <Skeleton className="mb-2 h-3 w-full" />
                  <Skeleton className="mb-2 h-3 w-5/6" />
                  <Skeleton className="h-3 w-2/3" />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={`target-skeleton-${i}`} className="card p-5">
                  <Skeleton className="mb-3 h-3 w-36" />
                  <Skeleton className="mb-2 h-8 w-28" />
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
