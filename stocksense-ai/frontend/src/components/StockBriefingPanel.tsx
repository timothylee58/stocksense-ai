"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, RefreshCw, Sparkles, AlertTriangle, Users, TrendingUp, FileText } from "lucide-react";
import { BriefingResponse, BriefingSection } from "@/types/stock";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SECTION_META: {
  key: keyof Pick<BriefingResponse, "sector_context" | "risk_flags" | "peer_comparison" | "analyst_framing">;
  label: string;
  icon: React.ReactNode;
  accent: string;
}[] = [
  { key: "sector_context",  label: "SECTOR CONTEXT",   icon: <TrendingUp size={12} />,     accent: "#0099ff" },
  { key: "risk_flags",      label: "RISK FLAGS",        icon: <AlertTriangle size={12} />,  accent: "#ff4560" },
  { key: "peer_comparison", label: "PEER COMPARISON",   icon: <Users size={12} />,          accent: "#a78bfa" },
  { key: "analyst_framing", label: "ANALYST FRAMING",   icon: <FileText size={12} />,       accent: "#f5a623" },
];

function BriefingSectionCard({
  title,
  icon,
  accent,
  section,
}: {
  title: string;
  icon: React.ReactNode;
  accent: string;
  section: BriefingSection;
}) {
  return (
    <div
      className="rounded-lg p-4"
      style={{
        background: `${accent}06`,
        border: `1px solid ${accent}20`,
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span style={{ color: accent }}>{icon}</span>
        <span
          className="tracking-widest"
          style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 9, color: accent, opacity: 0.7 }}
        >
          {title}
        </span>
      </div>
      <p
        className="mb-3 font-semibold leading-snug"
        style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 11, color: "#c8e0f4" }}
      >
        {section.headline}
      </p>
      <ul className="space-y-1.5">
        {section.bullets.map((bullet, i) => (
          <li
            key={i}
            className="flex gap-2 items-start"
            style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 10, color: "#6a90b0", lineHeight: 1.5 }}
          >
            <ChevronRight size={9} className="mt-0.5 shrink-0" style={{ color: accent }} />
            {bullet}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SkeletonLine({ w }: { w: string }) {
  return (
    <motion.div
      className="rounded"
      style={{ height: 8, width: w, background: "rgba(255,255,255,0.06)" }}
      animate={{ opacity: [0.4, 0.8, 0.4] }}
      transition={{ duration: 1.5, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
    />
  );
}

function BriefingSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(4)].map((_, i) => (
        <div
          key={i}
          className="rounded-lg p-4 space-y-2"
          style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" }}
        >
          <SkeletonLine w="40%" />
          <SkeletonLine w="80%" />
          <SkeletonLine w="70%" />
          <SkeletonLine w="65%" />
          <SkeletonLine w="75%" />
        </div>
      ))}
    </div>
  );
}

export default function StockBriefingPanel({ ticker }: { ticker: string }) {
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchBriefing = useCallback(async (t: string, force = false) => {
    setLoading(true);
    setError(null);
    if (!force) setBriefing(null);
    try {
      const res = await fetch(`${API_URL}/api/briefing/${t}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      const json: BriefingResponse = await res.json();
      setBriefing(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Briefing unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBriefing(ticker);
  }, [ticker, fetchBriefing]);

  const generatedAt = briefing?.generated_at
    ? new Date(briefing.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className="card p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles size={13} style={{ color: "#00ffcc" }} />
          <span
            className="tracking-widest"
            style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 10, color: "rgba(0,255,200,0.5)" }}
          >
            // AI STOCK BRIEFING
          </span>
        </div>
        <div className="flex items-center gap-3">
          {generatedAt && !loading && (
            <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 9, color: "#2a5070" }}>
              {generatedAt}
            </span>
          )}
          <button
            onClick={() => fetchBriefing(ticker, true)}
            disabled={loading}
            className="flex items-center gap-1 px-2 py-1 rounded transition-opacity"
            style={{
              fontFamily: "Share Tech Mono, monospace",
              fontSize: 9,
              color: "#00ffcc",
              background: "rgba(0,255,200,0.06)",
              border: "1px solid rgba(0,255,200,0.2)",
              opacity: loading ? 0.4 : 1,
            }}
            title="Regenerate briefing"
          >
            <RefreshCw size={9} className={loading ? "animate-spin" : ""} />
            REFRESH
          </button>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {loading && (
          <motion.div
            key="skeleton"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <BriefingSkeleton />
          </motion.div>
        )}

        {error && !loading && (
          <motion.div
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center gap-3 py-6 text-center"
          >
            <AlertTriangle size={20} style={{ color: "#ff4560" }} />
            <p style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 10, color: "#ff6070" }}>
              {error}
            </p>
            <button
              onClick={() => fetchBriefing(ticker)}
              className="px-3 py-1.5 rounded text-xs"
              style={{
                fontFamily: "Share Tech Mono, monospace",
                fontSize: 9,
                color: "#00ffcc",
                background: "rgba(0,255,200,0.06)",
                border: "1px solid rgba(0,255,200,0.2)",
              }}
            >
              RETRY
            </button>
          </motion.div>
        )}

        {briefing && !loading && (
          <motion.div
            key={`briefing-${ticker}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="space-y-3"
          >
            {/* Overall summary */}
            <div
              className="rounded-lg px-4 py-3"
              style={{ background: "rgba(0,255,200,0.04)", border: "1px solid rgba(0,255,200,0.12)" }}
            >
              <p
                className="leading-relaxed"
                style={{ fontFamily: "Share Tech Mono, monospace", fontSize: 11, color: "#c8e0f4" }}
              >
                {briefing.overall_summary}
              </p>
            </div>

            {/* Four sections */}
            {SECTION_META.map(({ key, label, icon, accent }) => (
              <BriefingSectionCard
                key={key}
                title={label}
                icon={icon}
                accent={accent}
                section={briefing[key]}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
