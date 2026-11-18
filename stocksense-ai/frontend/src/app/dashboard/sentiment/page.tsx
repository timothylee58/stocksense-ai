"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { RefreshCw, ExternalLink, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useSentiment } from "@/hooks/useSentiment";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TICKERS = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "MAYBANK.KL", "PBBANK.KL"];

function sentimentColor(score: number): string {
  if (score > 0.2) return "#1F5E46";
  if (score < -0.2) return "#A33A31";
  return "#8A6430";
}

function sentimentLabel(score: number): string {
  if (score > 0.2) return "Bullish";
  if (score < -0.2) return "Bearish";
  return "Neutral";
}

function SentimentGauge({ score }: { score: number }) {
  const col = sentimentColor(score);
  const pctVal = ((score + 1) / 2) * 100;
  const circumference = 2 * Math.PI * 42;
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(23,25,30,0.06)" strokeWidth="10" />
          <motion.circle
            cx="50" cy="50" r="42"
            fill="none"
            stroke={col}
            strokeWidth="10"
            strokeLinecap="round"
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: circumference - (pctVal / 100) * circumference }}
            transition={{ type: "spring", stiffness: 60, damping: 15, delay: 0.2 }}
            style={{ strokeDasharray: circumference, filter: `drop-shadow(0 0 8px ${col})` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-black text-2xl" style={{ color: col, fontFamily: "'Iowan Old Style', Georgia, serif" }}>
            {score >= 0 ? "+" : ""}{score.toFixed(2)}
          </span>
          <span className="text-xs mt-0.5" style={{ color: col, fontFamily: "'Space Mono', monospace", opacity: 0.7 }}>
            {sentimentLabel(score)}
          </span>
        </div>
      </div>
      <span className="text-xs tracking-widest" style={{ fontFamily: "'Space Mono', monospace", color: "#9C978D" }}>
        FINBERT SCORE
      </span>
    </div>
  );
}

function Skeleton({ className }: { className?: string }) {
  return (
    <motion.div
      className={`rounded bg-white/5 ${className ?? ""}`}
      animate={{ opacity: [0.4, 0.8, 0.4] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
    />
  );
}

export default function SentimentPage() {
  const [ticker, setTicker] = useState("NVDA");
  const [hours, setHours] = useState(24);
  const { data, loading, error, refetch } = useSentiment(ticker, hours);

  return (
    <div className="min-h-screen" style={{ background: "#F6F4EF" }}>
      <nav className="sticky top-0 z-40 flex items-center justify-between px-6 py-3"
        style={{ background: "rgba(246,244,239,0.92)", backdropFilter: "blur(14px)", borderBottom: "1px solid rgba(31,94,70,0.06)" }}>
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ background: "#1F5E46", boxShadow: "0 0 8px #1F5E46" }} />
            <span className="serif text-[15px] font-semibold leading-none" style={{ color: "#17191E" }}>StockSense <span className="mono text-[8px] tracking-[0.16em] align-middle" style={{ color: "#9C978D" }}>AI</span></span>
          </Link>
          <Link href="/dashboard" className="mono text-xs opacity-40 hover:opacity-80 transition-opacity" style={{ color: "#3C3E44" }}>
            / dashboard
          </Link>
          <span className="mono text-xs" style={{ color: "#3C3E44" }}>/ sentiment</span>
        </div>
        <button onClick={refetch}
          className="flex items-center gap-2 px-3 py-1.5 rounded text-xs"
          style={{ background: "rgba(31,94,70,0.06)", border: "1px solid rgba(31,94,70,0.3)", color: "#1F5E46" }}>
          <RefreshCw size={12} />
          <span className="orb tracking-widest">Refresh</span>
        </button>
      </nav>

      <div className="p-5 space-y-5">
        <div>
          <h1 className="orb text-2xl font-semibold" style={{ color: "#17191E" }}>Sentiment analysis</h1>
          <p className="mono text-xs mt-1" style={{ color: "#9C978D" }}>
            FinBERT (ProsusAI/finbert) — financial sentiment from news headlines
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex gap-2 flex-wrap">
            {TICKERS.slice(0, 7).map((t) => (
              <button key={t} onClick={() => setTicker(t)}
                className="orb text-xs px-3 py-1.5 rounded transition-all"
                style={{
                  background: ticker === t ? "rgba(31,94,70,0.12)" : "#FFFFFF",
                  border: `1px solid ${ticker === t ? "rgba(31,94,70,0.4)" : "rgba(23,25,30,0.10)"}`,
                  color: ticker === t ? "#1F5E46" : "#6E7075",
                }}>
                {t}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            {[6, 12, 24, 48].map((h) => (
              <button key={h} onClick={() => setHours(h)}
                className="mono text-xs px-3 py-1.5 rounded transition-all"
                style={{
                  background: hours === h ? "rgba(66,81,168,0.1)" : "transparent",
                  border: `1px solid ${hours === h ? "rgba(66,81,168,0.4)" : "rgba(66,81,168,0.1)"}`,
                  color: hours === h ? "#4251A8" : "#6E7075",
                }}>
                {h}H
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="p-4 rounded-lg flex items-center gap-3 mono text-sm"
            style={{ background: "rgba(163,58,49,0.08)", border: "1px solid rgba(163,58,49,0.25)", color: "#A33A31" }}>
            <AlertTriangle size={16} />{error}
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <div className="card p-6"><Skeleton className="h-48 w-full" /></div>
            <div className="md:col-span-2 card p-6"><Skeleton className="h-48 w-full" /></div>
          </div>
        ) : data ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <div className="card p-6 flex flex-col items-center justify-center gap-4">
              <SentimentGauge score={data.finbert_score} />
              <div className="w-full space-y-2 mt-2">
                {[
                  { label: "NEWS COUNT",   value: String(data.news_count),                           color: "#4251A8" },
                  { label: "REDDIT SCORE", value: data.reddit_score?.toFixed(3) ?? "N/A",            color: "#6B5CA5" },
                  { label: "SOURCE",       value: data.source.toUpperCase(),                          color: "#6E7075" },
                  { label: "SCORED AT",    value: data.scored_at ? data.scored_at.slice(0, 16) : "live", color: "#9C978D" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="flex justify-between py-1.5 px-3 rounded"
                    style={{ background: "rgba(23,25,30,0.03)", border: "1px solid rgba(23,25,30,0.06)" }}>
                    <span className="mono" style={{ color: "#9C978D", fontSize: 9, letterSpacing: "0.1em" }}>{label}</span>
                    <span className="orb text-xs font-bold" style={{ color }}>{value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="md:col-span-2 card p-6">
              <div className="mono text-xs mb-4 tracking-widest uppercase" style={{ color: "#9C978D" }}>
                Top headlines · {ticker}
              </div>
              {data.top_headlines.length === 0 ? (
                <div className="p-4 rounded-lg" style={{ background: "rgba(66,81,168,0.04)", border: "1px solid rgba(66,81,168,0.1)" }}>
                  <p className="mono text-xs" style={{ color: "#9C978D" }}>
                    No headlines available. Configure <span style={{ color: "#8A6430" }}>NEWS_API_KEY</span> in backend <span style={{ color: "#8A6430" }}>.env</span>.
                  </p>
                </div>
              ) : (
                <ul className="space-y-3">
                  <AnimatePresence>
                    {data.top_headlines.map((h, i) => (
                      <motion.li
                        key={i}
                        initial={{ opacity: 0, x: -12 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.06, type: "spring", stiffness: 300, damping: 25 }}
                        className="p-3 rounded-lg"
                        style={{ background: "#FBFAF6", border: "1px solid rgba(23,25,30,0.06)" }}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="mono text-xs flex-1" style={{ color: "#3C3E44", lineHeight: 1.6 }}>{h.title}</p>
                          {h.url && (
                            <a href={h.url} target="_blank" rel="noopener noreferrer" style={{ color: "#4251A8" }}>
                              <ExternalLink size={12} />
                            </a>
                          )}
                        </div>
                        <div className="flex items-center justify-between mt-2">
                          <span className="mono" style={{ color: "#9C978D", fontSize: 9 }}>{h.source}</span>
                          {h.score != null && (
                            <span className="mono" style={{ color: sentimentColor(h.score), fontSize: 9 }}>
                              {h.score >= 0 ? "+" : ""}{h.score.toFixed(3)}
                            </span>
                          )}
                        </div>
                      </motion.li>
                    ))}
                  </AnimatePresence>
                </ul>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
