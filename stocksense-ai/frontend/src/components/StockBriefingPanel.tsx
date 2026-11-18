"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, RefreshCw, Sparkles, AlertTriangle, Users, TrendingUp, FileText } from "lucide-react";
import { BriefingResponse, BriefingSection } from "@/types/stock";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const C = {
  line: "#E6E2D9",
  ink: "#17191E",
  inkSoft: "#3C3E44",
  muted: "#6E7075",
  faint: "#9C978D",
  accent: "#1F5E46",
  accentSoft: "#E9F1EC",
  danger: "#A33A31",
  dangerSoft: "#F9EBE8",
  info: "#4251A8",
  infoSoft: "#ECEEF9",
  warn: "#8A6430",
  warnSoft: "#F7EFE1",
  plum: "#6B5CA5",
  plumSoft: "#F0EDF7",
  panel: "#FFFFFF",
  bg: "#F6F4EF",
};

const SECTION_META: {
  key: keyof Pick<BriefingResponse, "sector_context" | "risk_flags" | "peer_comparison" | "analyst_framing">;
  label: string;
  icon: React.ReactNode;
  accent: string;
  tint: string;
}[] = [
  { key: "sector_context",  label: "Sector context",   icon: <TrendingUp size={11} />,     accent: C.info,    tint: C.infoSoft },
  { key: "risk_flags",      label: "Risk flags",       icon: <AlertTriangle size={11} />,  accent: C.danger,  tint: C.dangerSoft },
  { key: "peer_comparison", label: "Peer comparison",  icon: <Users size={11} />,          accent: C.plum,    tint: C.plumSoft },
  { key: "analyst_framing", label: "Analyst framing",  icon: <FileText size={11} />,       accent: C.warn,    tint: C.warnSoft },
];

function BriefingSectionCard({
  title,
  icon,
  accent,
  tint,
  section,
}: {
  title: string;
  icon: React.ReactNode;
  accent: string;
  tint: string;
  section: BriefingSection;
}) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{ background: C.panel, borderColor: C.line }}
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full" style={{ background: tint, color: accent }}>
          {icon}
        </span>
        <span className="mono text-[9px] uppercase tracking-[0.16em]" style={{ color: C.faint }}>
          {title}
        </span>
      </div>
      <p className="mb-2.5 text-[13px] font-semibold leading-snug" style={{ color: C.ink }}>
        {section.headline}
      </p>
      <ul className="space-y-1.5">
        {section.bullets.map((bullet, i) => (
          <li
            key={i}
            className="flex items-start gap-2 text-[12px] leading-relaxed"
            style={{ color: C.muted }}
          >
            <ChevronRight size={11} className="mt-0.5 shrink-0" style={{ color: accent }} />
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
      style={{ height: 8, width: w, background: "rgba(23,25,30,0.06)" }}
      animate={{ opacity: [0.35, 0.7, 0.35] }}
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
          className="space-y-2 rounded-xl border p-4"
          style={{ background: C.panel, borderColor: C.line }}
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
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full" style={{ background: C.accentSoft, color: C.accent }}>
            <Sparkles size={11} />
          </span>
          <span className="mono text-[9px] uppercase tracking-[0.16em]" style={{ color: C.faint }}>
            AI stock briefing
          </span>
        </div>
        <div className="flex items-center gap-3">
          {generatedAt && !loading && (
            <span className="mono text-[9px]" style={{ color: C.faint }}>
              {generatedAt}
            </span>
          )}
          <button
            onClick={() => fetchBriefing(ticker, true)}
            disabled={loading}
            className="mono flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] uppercase tracking-[0.08em] transition-colors hover:bg-[#FBFAF6]"
            style={{
              color: C.accent,
              borderColor: C.line,
              background: C.panel,
              opacity: loading ? 0.4 : 1,
            }}
            title="Regenerate briefing"
          >
            <RefreshCw size={9} className={loading ? "animate-spin" : ""} />
            Refresh
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
            <AlertTriangle size={18} style={{ color: C.danger }} />
            <p className="text-[12px]" style={{ color: C.danger }}>
              {error}
            </p>
            <button
              onClick={() => fetchBriefing(ticker)}
              className="mono rounded-full border px-3 py-1.5 text-[9px] uppercase tracking-[0.08em]"
              style={{ color: C.accent, borderColor: C.line, background: C.panel }}
            >
              Retry
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
              className="rounded-xl px-4 py-3.5"
              style={{ background: C.accentSoft, border: `1px solid ${C.line}` }}
            >
              <p className="text-[13px] leading-relaxed" style={{ color: C.inkSoft }}>
                {briefing.overall_summary}
              </p>
            </div>

            {/* Four sections */}
            {SECTION_META.map(({ key, label, icon, accent, tint }) => (
              <BriefingSectionCard
                key={key}
                title={label}
                icon={icon}
                accent={accent}
                tint={tint}
                section={briefing[key]}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
