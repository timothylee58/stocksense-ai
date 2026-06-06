"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  TrendingUp, TrendingDown, Minus, RefreshCw, BarChart3,
  Filter, ArrowUpRight, ArrowDownRight, ChevronRight,
  AlertTriangle, Activity, Zap,
} from "lucide-react";
import Link from "next/link";
import { BursaStock, MarketSnapshot, SectorSnapshot, BursaPrediction } from "@/types/bursa";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SECTOR_COLORS: Record<string, string> = {
  Financials:          "#0099ff",
  Utilities:           "#a78bfa",
  Materials:           "#f5a623",
  Communication:       "#00ffcc",
  "Consumer Defensive": "#ff6b35",
  "Consumer Cyclical":  "#fbbf24",
  Healthcare:          "#34d399",
  Energy:              "#fb923c",
  Industrials:         "#94a3b8",
  Technology:          "#60a5fa",
};

function changeColor(pct: number) {
  if (pct > 0) return "#00ffcc";
  if (pct < 0) return "#ff4560";
  return "#f5a623";
}
function fmtPct(v: number) { return (v >= 0 ? "+" : "") + v.toFixed(2) + "%"; }
function fmtRM(v: number) { return v > 0 ? `RM ${v.toFixed(3)}` : "—"; }
function fmtVol(v: number) {
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v > 0 ? String(v) : "—";
}

// ── Clock ───────────────────────────────────────────────────────────────────
function MYTClock() {
  const [time, setTime] = useState("");
  useEffect(() => {
    const tick = () => setTime(
      new Date().toLocaleTimeString("en-MY", { timeZone: "Asia/Kuala_Lumpur", hour12: false })
    );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 11, color: "#00ffcc" }}>
      MYT {time}
    </span>
  );
}

// ── Skeleton ────────────────────────────────────────────────────────────────
function Skel({ className }: { className?: string }) {
  return (
    <motion.div
      className={`rounded ${className ?? ""}`}
      style={{ background: "rgba(255,255,255,0.05)" }}
      animate={{ opacity: [0.4, 0.8, 0.4] }}
      transition={{ duration: 1.5, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
    />
  );
}

// ── Mover chip (top strip) ──────────────────────────────────────────────────
function MoverChip({
  stock, onClick, isActive,
}: { stock: BursaStock; onClick: () => void; isActive: boolean }) {
  const col = changeColor(stock.change_pct);
  return (
    <motion.button
      onClick={onClick}
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      className="flex flex-col gap-0.5 px-3 py-2 rounded-lg shrink-0 text-left"
      style={{
        background: isActive ? `${col}10` : "rgba(0,12,28,0.8)",
        border: `1px solid ${isActive ? col : col + "30"}`,
        minWidth: 110,
        outline: isActive ? `1px solid ${col}50` : "none",
      }}
    >
      <div className="flex items-center justify-between gap-1">
        <span style={{ fontFamily: "Orbitron, monospace", fontSize: 10, color: col, fontWeight: 800 }}>
          {stock.ticker}
        </span>
        {stock.change_pct >= 0
          ? <TrendingUp size={9} style={{ color: col }} />
          : <TrendingDown size={9} style={{ color: col }} />}
      </div>
      <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 11, color: "#c8e0f4" }}>
        {fmtRM(stock.last_price)}
      </span>
      <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 9, color: col }}>
        {fmtPct(stock.change_pct)}
      </span>
    </motion.button>
  );
}

// ── Sector heatmap cell ─────────────────────────────────────────────────────
function SectorCell({
  data, active, onClick,
}: { data: SectorSnapshot; active: boolean; onClick: () => void }) {
  const col = data.color ?? SECTOR_COLORS[data.sector] ?? "#4a7090";
  const changeCol = changeColor(data.avg_change);
  return (
    <motion.button
      onClick={onClick}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      className="flex flex-col gap-1 p-3 rounded-lg text-left w-full"
      style={{
        background: active ? `${col}18` : `${col}08`,
        border: `1px solid ${active ? col + "60" : col + "20"}`,
      }}
    >
      <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 8, color: col, letterSpacing: "0.12em" }}>
        {data.sector.toUpperCase()}
      </span>
      <span style={{ fontFamily: "Orbitron, monospace", fontSize: 14, color: changeCol, fontWeight: 700 }}>
        {fmtPct(data.avg_change)}
      </span>
      <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 9, color: "#2a5070" }}>
        {data.count} stock{data.count !== 1 ? "s" : ""}
      </span>
    </motion.button>
  );
}

// ── Screener table ──────────────────────────────────────────────────────────
function ScreenerRow({
  stock, active, onClick,
}: { stock: BursaStock; active: boolean; onClick: () => void }) {
  const col = changeColor(stock.change_pct);
  const sCol = SECTOR_COLORS[stock.sector] ?? "#4a7090";
  return (
    <motion.tr
      onClick={onClick}
      whileHover={{ backgroundColor: "rgba(0,153,255,0.04)" }}
      className="cursor-pointer"
      style={{
        borderBottom: "1px solid rgba(255,255,255,0.03)",
        background: active ? "rgba(0,255,200,0.04)" : "transparent",
      }}
    >
      <td className="py-2.5 px-3">
        <div className="flex items-center gap-2">
          {active && <div className="w-1 h-4 rounded-full" style={{ background: "#00ffcc" }} />}
          <span style={{ fontFamily: "Orbitron, monospace", fontSize: 10, color: col, fontWeight: 800 }}>
            {stock.ticker}
          </span>
        </div>
      </td>
      <td className="py-2.5 px-3">
        <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 10, color: "#c8e0f4" }}>
          {stock.name}
        </span>
      </td>
      <td className="py-2.5 px-3">
        <span className="px-1.5 py-0.5 rounded"
          style={{ fontSize: 8, fontFamily: "Share Tech Mono, monospace", background: `${sCol}12`, color: sCol, border: `1px solid ${sCol}25` }}>
          {stock.sector}
        </span>
      </td>
      <td className="py-2.5 px-3 text-right">
        <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 11, color: "#c8e0f4" }}>
          {stock.last_price > 0 ? stock.last_price.toFixed(3) : "—"}
        </span>
      </td>
      <td className="py-2.5 px-3 text-right">
        <span className="flex items-center justify-end gap-1" style={{ color: col, fontSize: 11, fontFamily: "Share Tech Mono, monospace" }}>
          {stock.change_pct > 0 ? <TrendingUp size={10} /> : stock.change_pct < 0 ? <TrendingDown size={10} /> : <Minus size={10} />}
          {fmtPct(stock.change_pct)}
        </span>
      </td>
      <td className="py-2.5 px-3 text-right">
        <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 10, color: "#6a90b0" }}>
          {fmtVol(stock.volume)}
        </span>
      </td>
    </motion.tr>
  );
}

// ── Live quote detail ────────────────────────────────────────────────────────
function QuoteDetail({ quote }: { quote: BursaStock }) {
  const col = changeColor(quote.change_pct);
  const rows = [
    ["OPEN",       fmtRM(quote.open_price)],
    ["HIGH",       fmtRM(quote.high_price)],
    ["LOW",        fmtRM(quote.low_price)],
    ["PREV CLOSE", fmtRM(quote.prev_close_price)],
    ["BID",        quote.bid_price > 0 ? fmtRM(quote.bid_price) : "—"],
    ["ASK",        quote.ask_price > 0 ? fmtRM(quote.ask_price) : "—"],
    ["VOLUME",     fmtVol(quote.volume)],
    ["CHANGE",     `${fmtRM(quote.change_abs)} (${fmtPct(quote.change_pct)})`],
  ];
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-4 rounded-lg"
      style={{ background: "rgba(0,12,28,0.8)", border: "1px solid rgba(0,153,255,0.1)" }}
    >
      <div className="mono mb-3" style={{ fontSize: 9, color: "rgba(0,255,200,0.4)", letterSpacing: "0.2em" }}>
        // LIVE QUOTE
      </div>
      <div className="flex items-end gap-3 mb-4">
        <span className="orb font-black" style={{ fontSize: 26, color: col, lineHeight: 1 }}>
          {fmtRM(quote.last_price)}
        </span>
        <span className="mb-0.5 mono" style={{ fontSize: 12, color: col }}>
          {fmtPct(quote.change_pct)}
        </span>
        {quote.source === "yfinance_kl" && (
          <span className="mb-1 px-1.5 py-0.5 rounded mono" style={{ fontSize: 8, background: "rgba(245,166,35,0.1)", color: "#f5a623", border: "1px solid rgba(245,166,35,0.2)" }}>
            DELAYED
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between items-center px-2 py-1.5 rounded"
            style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)" }}>
            <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 8, color: "#2a5070", letterSpacing: "0.1em" }}>{label}</span>
            <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 10, color: "#c8e0f4" }}>{value}</span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

// ── ML Prediction card ──────────────────────────────────────────────────────
function PredictionCard({ pred }: { pred: BursaPrediction }) {
  const col = pred.direction === "UP" ? "#00ffcc" : pred.direction === "DOWN" ? "#ff4560" : "#f5a623";
  const indicators = [
    { label: "RSI", value: pred.rsi != null ? pred.rsi.toFixed(1) : "—", color: (pred.rsi ?? 50) < 30 ? "#00ffcc" : (pred.rsi ?? 50) > 70 ? "#ff4560" : "#f5a623" },
    { label: "MACD", value: pred.macd != null ? ((pred.macd >= 0 ? "+" : "") + pred.macd.toFixed(3)) : "—", color: (pred.macd ?? 0) >= 0 ? "#00ffcc" : "#ff4560" },
    { label: "MOM 5D", value: pred.momentum_5d != null ? fmtPct(pred.momentum_5d) : "—", color: changeColor(pred.momentum_5d ?? 0) },
    { label: "VOL ×", value: pred.vol_ratio != null ? `${pred.vol_ratio.toFixed(1)}×` : "—", color: (pred.vol_ratio ?? 1) > 1.5 ? "#00ffcc" : "#6a90b0" },
  ];
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-4 rounded-lg space-y-4"
      style={{ background: "rgba(0,12,28,0.8)", border: "1px solid rgba(0,153,255,0.1)" }}
    >
      <div className="mono" style={{ fontSize: 9, color: "rgba(0,255,200,0.4)", letterSpacing: "0.2em" }}>
        // ML PREDICTION
      </div>
      {/* Direction + Confidence */}
      <div className="flex items-center gap-4">
        <div className="flex flex-col items-center justify-center w-20 h-20 rounded-xl"
          style={{ background: `${col}10`, border: `1px solid ${col}35` }}>
          {pred.direction === "UP"
            ? <ArrowUpRight size={28} style={{ color: col }} />
            : <ArrowDownRight size={28} style={{ color: col }} />}
          <span className="orb font-black" style={{ fontSize: 10, color: col, marginTop: 2 }}>
            {pred.direction}
          </span>
        </div>
        <div className="flex-1 space-y-2">
          <div className="mono" style={{ fontSize: 8, color: "#2a5070", letterSpacing: "0.15em" }}>CONFIDENCE</div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${pred.confidence * 100}%` }}
              transition={{ duration: 0.9, ease: "easeOut" }}
              className="h-full rounded-full"
              style={{ background: col, boxShadow: `0 0 8px ${col}80` }}
            />
          </div>
          <div className="orb font-bold" style={{ fontSize: 16, color: col }}>
            {(pred.confidence * 100).toFixed(0)}%
          </div>
        </div>
      </div>
      {/* Indicator grid */}
      <div className="grid grid-cols-2 gap-1.5">
        {indicators.map(({ label, value, color }) => (
          <div key={label} className="text-center p-2 rounded"
            style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.05)" }}>
            <div className="mono" style={{ fontSize: 8, color: "#2a5070", letterSpacing: "0.1em" }}>{label}</div>
            <div className="orb font-bold" style={{ fontSize: 11, color, marginTop: 2 }}>{value}</div>
          </div>
        ))}
      </div>
      {/* Signal bullets */}
      {pred.signals.length > 0 && (
        <div>
          <div className="mono mb-2" style={{ fontSize: 8, color: "#2a5070", letterSpacing: "0.15em" }}>SIGNALS</div>
          <ul className="space-y-1.5">
            {pred.signals.map((s, i) => (
              <li key={i} className="flex gap-2 items-start mono" style={{ fontSize: 9, color: "#6a90b0", lineHeight: 1.5 }}>
                <ChevronRight size={9} className="mt-0.5 shrink-0" style={{ color: col }} />
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}
      {pred.error && (
        <p className="mono" style={{ fontSize: 9, color: "#ff6070" }}>{pred.error}</p>
      )}
    </motion.div>
  );
}

// ── Dashboard ────────────────────────────────────────────────────────────────
export default function BursaSensPage() {
  const [market, setMarket]           = useState<MarketSnapshot | null>(null);
  const [screened, setScreened]       = useState<BursaStock[]>([]);
  const [activeCode, setActiveCode]   = useState<string | null>(null);
  const [liveQuote, setLiveQuote]     = useState<BursaStock | null>(null);
  const [prediction, setPrediction]   = useState<BursaPrediction | null>(null);
  const [loadingMkt, setLoadingMkt]   = useState(true);
  const [loadingPred, setLoadingPred] = useState(false);
  const [sectorFilter, setSectorFilter] = useState("");
  const [sortBy, setSortBy]           = useState<"change_pct" | "volume" | "last_price">("change_pct");
  const [error, setError]             = useState<string | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  const fetchMarket = useCallback(async () => {
    setLoadingMkt(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/bursa/market`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: MarketSnapshot = await res.json();
      setMarket(json);
      setScreened(json.quotes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load market data");
    } finally {
      setLoadingMkt(false);
    }
  }, []);

  useEffect(() => { fetchMarket(); }, [fetchMarket]);

  // Client-side screener filter
  useEffect(() => {
    if (!market) return;
    let list = [...market.quotes];
    if (sectorFilter) list = list.filter(s => s.sector === sectorFilter);
    list.sort((a, b) => {
      if (sortBy === "volume") return b.volume - a.volume;
      if (sortBy === "last_price") return b.last_price - a.last_price;
      return b.change_pct - a.change_pct;
    });
    setScreened(list);
  }, [market, sectorFilter, sortBy]);

  const selectCode = useCallback(async (code: string) => {
    setActiveCode(code);
    setPrediction(null);
    setLiveQuote(market?.quotes.find(s => s.code === code) ?? null);

    // SSE
    sseRef.current?.close();
    const sse = new EventSource(`${API_URL}/api/bursa/stream?code=${code}`);
    sse.onmessage = (e) => {
      try {
        const d: BursaStock = JSON.parse(e.data);
        if (!("error" in d)) setLiveQuote(d);
      } catch {}
    };
    sseRef.current = sse;

    // Prediction
    setLoadingPred(true);
    try {
      const res = await fetch(`${API_URL}/api/bursa/predict/${code}`);
      if (res.ok) setPrediction(await res.json());
    } catch {}
    finally { setLoadingPred(false); }
  }, [market]);

  useEffect(() => () => sseRef.current?.close(), []);

  const sectors = market ? [...new Set(market.quotes.map(s => s.sector))].sort() : [];
  const movers = market ? [...market.gainers, ...market.losers] : [];

  return (
    <div className="min-h-screen" style={{ background: "#030d1a", fontFamily: "Share Tech Mono, monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');
        .orb  { font-family: 'Orbitron', monospace; }
        .mono { font-family: 'Share Tech Mono', monospace; }
        .card { background: rgba(0,12,28,0.8); border: 1px solid rgba(0,153,255,0.1); border-radius: 12px; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(245,166,35,0.2); border-radius: 2px; }
      `}</style>

      {/* ── Nav ───────────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-40 flex items-center justify-between px-6 py-3"
        style={{ background: "rgba(3,13,26,0.95)", borderBottom: "1px solid rgba(245,166,35,0.12)", backdropFilter: "blur(14px)" }}>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full" style={{ background: "#f5a623", boxShadow: "0 0 10px #f5a623" }} />
            <span className="orb font-black text-sm tracking-widest" style={{ color: "#f5a623" }}>BURSA</span>
            <span className="orb font-black text-sm tracking-widest" style={{ color: "#00ffcc" }}>&amp;SENS</span>
          </div>
          <span className="mono px-2 py-0.5 rounded"
            style={{ fontSize: 9, background: "rgba(245,166,35,0.08)", border: "1px solid rgba(245,166,35,0.2)", color: "#f5a623", letterSpacing: "0.15em" }}>
            KLSE · BURSA MALAYSIA
          </span>
          {market && (
            <span className="mono" style={{ fontSize: 10, color: "#2a5070" }}>
              {market.active}/{market.total} tracked
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <MYTClock />
          <button onClick={fetchMarket} disabled={loadingMkt}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded transition-opacity"
            style={{ background: "rgba(245,166,35,0.06)", border: "1px solid rgba(245,166,35,0.25)", color: "#f5a623", fontSize: 9, opacity: loadingMkt ? 0.5 : 1 }}>
            <RefreshCw size={9} className={loadingMkt ? "animate-spin" : ""} />
            REFRESH
          </button>
          <Link href="/dashboard"
            className="mono px-3 py-1.5 rounded"
            style={{ background: "rgba(0,153,255,0.06)", border: "1px solid rgba(0,153,255,0.2)", color: "#0099ff", fontSize: 9 }}>
            ← STOCKSENSE
          </Link>
        </div>
      </nav>

      <div className="px-6 py-6 space-y-6 max-w-[1700px] mx-auto">

        {/* ── Error ─────────────────────────────────────────────────────── */}
        {error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex items-center gap-3 p-4 rounded-lg"
            style={{ background: "rgba(255,69,96,0.06)", border: "1px solid rgba(255,69,96,0.2)" }}>
            <AlertTriangle size={14} style={{ color: "#ff4560" }} />
            <span className="mono" style={{ fontSize: 10, color: "#ff8094" }}>{error}</span>
            <button onClick={fetchMarket} className="mono ml-auto px-2 py-1 rounded"
              style={{ fontSize: 9, border: "1px solid rgba(255,69,96,0.3)", color: "#ff4560" }}>
              RETRY
            </button>
          </motion.div>
        )}

        {/* ── Movers strip ──────────────────────────────────────────────── */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Zap size={10} style={{ color: "#f5a623" }} />
            <span className="mono" style={{ fontSize: 9, color: "#2a5070", letterSpacing: "0.15em" }}>
              // TOP MOVERS
            </span>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {loadingMkt
              ? Array.from({ length: 10 }).map((_, i) => (
                  <div key={i} className="shrink-0 rounded-lg" style={{ width: 110, height: 70, background: "rgba(255,255,255,0.05)" }}>
                    <Skel className="w-full h-full" />
                  </div>
                ))
              : movers.map(s => (
                  <MoverChip key={s.code} stock={s} isActive={s.code === activeCode} onClick={() => selectCode(s.code)} />
                ))
            }
          </div>
        </div>

        {/* ── Main grid ─────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

          {/* Left: Screener ─────────────────────────────────────────────── */}
          <div className="xl:col-span-2 space-y-4">

            {/* Controls */}
            <div className="card p-4 flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <Filter size={10} style={{ color: "#0099ff" }} />
                <span className="mono" style={{ fontSize: 9, color: "#2a5070", letterSpacing: "0.15em" }}>SCREENER</span>
              </div>

              <select value={sectorFilter} onChange={e => setSectorFilter(e.target.value)}
                className="px-2 py-1 rounded"
                style={{ background: "rgba(0,12,28,0.9)", border: "1px solid rgba(0,153,255,0.2)", color: "#c8e0f4", fontSize: 10, fontFamily: "Share Tech Mono, monospace" }}>
                <option value="">All Sectors</option>
                {sectors.map(s => <option key={s} value={s}>{s}</option>)}
              </select>

              <select value={sortBy} onChange={e => setSortBy(e.target.value as typeof sortBy)}
                className="px-2 py-1 rounded"
                style={{ background: "rgba(0,12,28,0.9)", border: "1px solid rgba(0,153,255,0.2)", color: "#c8e0f4", fontSize: 10, fontFamily: "Share Tech Mono, monospace" }}>
                <option value="change_pct">Sort: Change %</option>
                <option value="volume">Sort: Volume</option>
                <option value="last_price">Sort: Price</option>
              </select>

              {sectorFilter && (
                <button onClick={() => setSectorFilter("")}
                  className="mono px-2 py-1 rounded"
                  style={{ fontSize: 9, color: "#f5a623", border: "1px solid rgba(245,166,35,0.3)" }}>
                  ✕ {sectorFilter}
                </button>
              )}

              <span className="mono ml-auto" style={{ fontSize: 9, color: "#2a5070" }}>
                {screened.length} stocks
              </span>
            </div>

            {/* Table */}
            <div className="card p-4 overflow-x-auto">
              {loadingMkt ? (
                <div className="space-y-2">
                  {Array.from({ length: 10 }).map((_, i) => <Skel key={i} className="h-9 w-full" />)}
                </div>
              ) : screened.length === 0 ? (
                <div className="flex flex-col items-center py-10 gap-3"
                  style={{ color: "#2a5070" }}>
                  <Filter size={20} />
                  <span className="mono" style={{ fontSize: 11 }}>No stocks match filters</span>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr>
                      {["CODE", "COMPANY", "SECTOR", "PRICE (RM)", "CHANGE", "VOLUME"].map(h => (
                        <th key={h} className={`text-left pb-3 px-3 ${h === "PRICE (RM)" || h === "CHANGE" || h === "VOLUME" ? "text-right" : ""}`}
                          style={{ fontSize: 8, fontFamily: "Share Tech Mono, monospace", color: "#2a5070", letterSpacing: "0.15em", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {screened.map(s => (
                      <ScreenerRow key={s.code} stock={s} active={s.code === activeCode} onClick={() => selectCode(s.code)} />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Right: Sector heatmap + detail ─────────────────────────────── */}
          <div className="space-y-4">
            {/* Sector heatmap */}
            <div className="card p-4">
              <div className="flex items-center gap-2 mb-3">
                <Activity size={10} style={{ color: "#00ffcc" }} />
                <span className="mono" style={{ fontSize: 9, color: "rgba(0,255,200,0.4)", letterSpacing: "0.2em" }}>
                  // SECTOR HEATMAP
                </span>
              </div>
              {loadingMkt ? (
                <div className="grid grid-cols-2 gap-2">
                  {Array.from({ length: 6 }).map((_, i) => <Skel key={i} className="h-16" />)}
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {(market?.sectors ?? []).map(s => (
                    <SectorCell
                      key={s.sector}
                      data={s}
                      active={sectorFilter === s.sector}
                      onClick={() => setSectorFilter(prev => prev === s.sector ? "" : s.sector)}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Stock detail */}
            <AnimatePresence mode="wait">
              {activeCode ? (
                <motion.div key={activeCode} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                  className="space-y-4">
                  {/* Header */}
                  <div className="card p-3 flex items-center justify-between">
                    <div>
                      <div className="mono mb-0.5" style={{ fontSize: 8, color: "#2a5070" }}>SELECTED</div>
                      <div className="flex items-center gap-2">
                        <span className="orb font-black" style={{ fontSize: 15, color: "#f5a623" }}>
                          {activeCode.split(".")[1]}
                        </span>
                        <span className="mono" style={{ fontSize: 9, color: "#6a90b0" }}>
                          {liveQuote?.name ?? ""}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "#00ffcc" }} />
                      <span className="mono" style={{ fontSize: 8, color: "#00ffcc" }}>LIVE</span>
                    </div>
                  </div>

                  {liveQuote ? (
                    <QuoteDetail quote={liveQuote} />
                  ) : (
                    <div className="card p-4 space-y-2">
                      <Skel className="h-8 w-32 mb-3" />
                      {Array.from({ length: 4 }).map((_, i) => <Skel key={i} className="h-6 w-full" />)}
                    </div>
                  )}

                  {loadingPred ? (
                    <div className="card p-4 space-y-3">
                      <Skel className="h-4 w-40" />
                      <div className="flex gap-3">
                        <Skel className="h-20 w-20 rounded-xl" />
                        <div className="flex-1 space-y-2">
                          <Skel className="h-3 w-full" />
                          <Skel className="h-2 w-full" />
                          <Skel className="h-5 w-16" />
                        </div>
                      </div>
                    </div>
                  ) : prediction ? (
                    <PredictionCard pred={prediction} />
                  ) : null}
                </motion.div>
              ) : !loadingMkt ? (
                <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  className="card p-8 flex flex-col items-center gap-4 text-center">
                  <BarChart3 size={28} style={{ color: "#1a3550" }} />
                  <div>
                    <p className="orb font-bold mb-1" style={{ fontSize: 11, color: "#2a5070" }}>
                      SELECT A STOCK
                    </p>
                    <p className="mono" style={{ fontSize: 9, color: "#1a3550" }}>
                      Click a row or mover chip to see live quote and ML direction prediction.
                    </p>
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        </div>

        {/* ── Footer ────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between pt-2 pb-4"
          style={{ borderTop: "1px solid rgba(0,153,255,0.06)" }}>
          <span className="mono" style={{ fontSize: 9, color: "#1a3550" }}>
            Bursa&amp;Sens · Powered by moomoo OpenAPI + FinBERT · Data may be delayed
          </span>
          {market && (
            <span className="mono" style={{ fontSize: 9, color: "#1a3550" }}>
              Last updated {new Date(market.timestamp).toLocaleTimeString("en-MY", { timeZone: "Asia/Kuala_Lumpur" })} MYT
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
