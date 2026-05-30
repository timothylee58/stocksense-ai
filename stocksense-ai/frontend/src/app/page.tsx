"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";

// ─── 3D Neural Network ────────────────────────────────────────────────────────
// Pure math: rotates nodes in 3D, projects to 2D with perspective. No libraries.

const LAYERS = [4, 6, 6, 2];
const LAYER_COLORS = ["#00ffcc", "#0099ff", "#0099ff", "#ff6b35"];
const RING_R = 70;
const LAYER_GAP = 138;
const FOV = 720;
const SVG_W = 560;
const SVG_H = 400;

type Pt3 = { x: number; y: number; z: number; layer: number };
type Projected = Pt3 & { px: number; py: number; depth: number; scale: number };

function buildNetwork(): { nodes: Pt3[]; edges: [number, number][] } {
  const nodes: Pt3[] = [];
  LAYERS.forEach((count, li) => {
    const x = (li - (LAYERS.length - 1) / 2) * LAYER_GAP;
    for (let i = 0; i < count; i++) {
      const a = (i / count) * Math.PI * 2 - Math.PI / 2;
      nodes.push({ x, y: count > 1 ? Math.sin(a) * RING_R : 0, z: count > 1 ? Math.cos(a) * RING_R : 0, layer: li });
    }
  });
  const edges: [number, number][] = [];
  let off = 0;
  LAYERS.forEach((cnt, li) => {
    if (li < LAYERS.length - 1) {
      const nextOff = off + cnt;
      for (let i = 0; i < cnt; i++)
        for (let j = 0; j < LAYERS[li + 1]; j++)
          edges.push([off + i, nextOff + j]);
    }
    off += cnt;
  });
  return { nodes, edges };
}

const { nodes: NET_NODES, edges: NET_EDGES } = buildNetwork();

function projectPt(n: Pt3, ry: number): Projected {
  const cos = Math.cos(ry), sin = Math.sin(ry);
  const rx = n.x * cos - n.z * sin;
  const rz = n.x * sin + n.z * cos;
  const s = FOV / (FOV + rz + 380);
  return { ...n, px: SVG_W / 2 + rx * s, py: SVG_H / 2 + n.y * s, depth: rz, scale: s };
}

function NeuralNet3D() {
  const [angle, setAngle] = useState(0.4);

  useEffect(() => {
    let id: number;
    let a = 0.4;
    const tick = () => { a += 0.006; setAngle(a); id = requestAnimationFrame(tick); };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, []);

  const pts: Projected[] = useMemo(
    () => NET_NODES.map((n) => projectPt(n, angle)),
    [angle]
  );

  const sortedEdges = useMemo(
    () => [...NET_EDGES].sort((a, b) => {
      const da = (pts[a[0]].depth + pts[a[1]].depth) / 2;
      const db = (pts[b[0]].depth + pts[b[1]].depth) / 2;
      return da - db;
    }),
    [pts]
  );

  return (
    <svg
      width={SVG_W}
      height={SVG_H}
      aria-label="3D neural network visualization"
      style={{ filter: "drop-shadow(0 0 50px rgba(0,255,200,0.10))" }}
    >
      <defs>
        <filter id="nn-glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <radialGradient id="bg-halo" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#00ffcc" stopOpacity="0.04" />
          <stop offset="100%" stopColor="#00ffcc" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* background halo */}
      <ellipse cx={SVG_W / 2} cy={SVG_H / 2} rx={240} ry={180} fill="url(#bg-halo)" />

      {/* edges */}
      {sortedEdges.map(([a, b], i) => {
        const pa = pts[a], pb = pts[b];
        const d = (pa.depth + pb.depth) / 2;
        const op = Math.max(0.02, Math.min(0.22, (d + 360) / 750));
        return (
          <line key={i}
            x1={pa.px} y1={pa.py} x2={pb.px} y2={pb.py}
            stroke={LAYER_COLORS[pa.layer]} strokeWidth={0.55} strokeOpacity={op}
          />
        );
      })}

      {/* nodes */}
      {pts.map((p, i) => {
        const col = LAYER_COLORS[p.layer];
        const r = Math.max(2.5, 7 * p.scale);
        const op = Math.max(0.2, Math.min(1, (p.depth + 400) / 620));
        return (
          <g key={i} filter="url(#nn-glow)" opacity={op}>
            <circle cx={p.px} cy={p.py} r={r * 3.2} fill={col} fillOpacity={0.06} />
            <circle cx={p.px} cy={p.py} r={r} fill={col} />
          </g>
        );
      })}
    </svg>
  );
}

// ─── Page Data ────────────────────────────────────────────────────────────────

const STEPS = [
  {
    num: "01",
    tag: "ML TRAINING",
    tagColor: "#00ffcc",
    prefix: "curl -X POST localhost:8000",
    cmd: "/api/train/AAPL",
    desc: "Train your first LSTM + XGBoost ensemble model on 2 years of daily AAPL market data. Models are saved with versioned timestamps and auto-aliased as latest.",
  },
  {
    num: "02",
    tag: "LOCAL DEV",
    tagColor: "#0099ff",
    prefix: "$",
    cmd: "docker compose up",
    desc: "Boot the full stack in one command — FastAPI backend, Next.js frontend, Redis cache, and PostgreSQL database all wired together with shared volumes.",
  },
  {
    num: "03",
    tag: "CI / CD",
    tagColor: "#a78bfa",
    prefix: "$",
    cmd: "git push origin main",
    desc: "GitHub Actions runs automatically: backend lint with ruff, TypeScript type-check, Next.js build, and Docker image builds for both services.",
  },
  {
    num: "04",
    tag: "AUTO-DEPLOY",
    tagColor: "#ff6b35",
    prefix: "github secrets →",
    cmd: "VERCEL_TOKEN  ·  VERCEL_ORG_ID\nVERCEL_PROJECT_ID  ·  RAILWAY_TOKEN",
    desc: "Add these 4 secrets to your GitHub repository. On every merge to main, frontend auto-deploys to Vercel and backend auto-deploys to Railway.",
  },
];

const FEATURES = [
  { icon: "◈", col: "#00ffcc", title: "LSTM + XGBoost Ensemble", desc: "60 % LSTM weight + 40 % XGBoost. Falls back gracefully to rule-based signal when no model artifacts exist." },
  { icon: "⬡", col: "#0099ff", title: "WebSocket Live Prices", desc: "Real-time streaming via /ws/ticker/{ticker}. 60 s interval during market hours, 300 s off-hours." },
  { icon: "◎", col: "#00ffcc", title: "Redis Caching", desc: "Dataset cached 15 min, predictions 5 min. Turns 3 s p95 latency into ~50 ms on cache hit." },
  { icon: "▲", col: "#ff6b35", title: "Technical Indicators", desc: "RSI-14, MACD-12/26/9, SMA-20/50 computed from 2 years of daily OHLCV data via pandas-ta." },
  { icon: "◆", col: "#a78bfa", title: "JWT Authentication", desc: "HMAC-SHA256 signed tokens, 24 h expiry, salted password hashing. Register + login endpoints ready." },
  { icon: "⬤", col: "#0099ff", title: "Full DevOps Stack", desc: "Docker Compose + multi-stage Dockerfiles + GitHub Actions CI with lint, type-check, and image builds." },
];

const STATS = [
  { label: "Models", value: "LSTM + XGB" },
  { label: "Ensemble", value: "60% / 40%" },
  { label: "Cache TTL", value: "15 / 5 min" },
  { label: "API Routes", value: "12 endpoints" },
  { label: "Data Window", value: "2yr daily" },
  { label: "Deploy", value: "Vercel + Railway" },
];

// ─── Landing Page ─────────────────────────────────────────────────────────────

export default function LandingPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <div
      className="min-h-screen text-white overflow-x-hidden"
      style={{
        background: "#030d1a",
        backgroundImage:
          "linear-gradient(rgba(0,255,200,0.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,255,200,0.025) 1px,transparent 1px)",
        backgroundSize: "52px 52px",
      }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');
        .orb { font-family: 'Orbitron', monospace; }
        .mono { font-family: 'Share Tech Mono', monospace; }

        @keyframes pulse-dot {
          0%,100% { opacity:1; transform:scale(1); }
          50%      { opacity:0.6; transform:scale(1.4); }
        }
        @keyframes fadein-up {
          from { opacity:0; transform:translateY(28px); }
          to   { opacity:1; transform:translateY(0); }
        }
        @keyframes blink {
          0%,100% { opacity:1; }
          50%      { opacity:0; }
        }
        @keyframes scan {
          0%   { transform:translateY(0); opacity:0.06; }
          100% { transform:translateY(100vh); opacity:0; }
        }
        @keyframes glow-pulse {
          0%,100% { box-shadow: 0 0 20px rgba(0,255,200,0.25), inset 0 0 20px rgba(0,255,200,0.05); }
          50%      { box-shadow: 0 0 40px rgba(0,255,200,0.45), inset 0 0 30px rgba(0,255,200,0.1); }
        }

        .fade-1 { animation: fadein-up 0.7s ease 0.1s both; }
        .fade-2 { animation: fadein-up 0.7s ease 0.25s both; }
        .fade-3 { animation: fadein-up 0.7s ease 0.45s both; }
        .fade-4 { animation: fadein-up 0.7s ease 0.65s both; }

        .step-row {
          border-top: 1px solid rgba(0,255,200,0.06);
          transition: background 0.25s;
        }
        .step-row:hover { background: rgba(0,255,200,0.02); }

        .feat-card {
          border: 1px solid rgba(0,153,255,0.09);
          background: rgba(0,12,28,0.7);
          transition: border-color 0.3s, transform 0.25s, background 0.3s;
        }
        .feat-card:hover {
          border-color: rgba(0,255,200,0.28);
          background: rgba(0,20,45,0.85);
          transform: translateY(-3px);
        }

        .primary-btn {
          background: rgba(0,255,200,0.08);
          border: 1px solid #00ffcc;
          color: #00ffcc;
          animation: glow-pulse 3s ease-in-out infinite;
          transition: transform 0.2s;
        }
        .primary-btn:hover { transform: translateY(-2px); }

        .secondary-btn {
          background: transparent;
          border: 1px solid rgba(0,153,255,0.35);
          color: #0099ff;
          transition: border-color 0.3s, transform 0.2s;
        }
        .secondary-btn:hover { border-color: rgba(0,153,255,0.7); transform: translateY(-2px); }

        .corner-tl { position:absolute; top:0; left:0; width:18px; height:18px; border-top:1px solid rgba(0,255,200,0.3); border-left:1px solid rgba(0,255,200,0.3); }
        .corner-tr { position:absolute; top:0; right:0; width:18px; height:18px; border-top:1px solid rgba(0,255,200,0.3); border-right:1px solid rgba(0,255,200,0.3); }
        .corner-bl { position:absolute; bottom:0; left:0; width:18px; height:18px; border-bottom:1px solid rgba(0,255,200,0.3); border-left:1px solid rgba(0,255,200,0.3); }
        .corner-br { position:absolute; bottom:0; right:0; width:18px; height:18px; border-bottom:1px solid rgba(0,255,200,0.3); border-right:1px solid rgba(0,255,200,0.3); }
      `}</style>

      {/* scan line effect */}
      <div
        className="pointer-events-none fixed inset-x-0 top-0 h-32 z-50"
        style={{
          background: "linear-gradient(to bottom, rgba(0,255,200,0.04), transparent)",
          animation: "scan 8s linear infinite",
        }}
      />

      {/* ── NAV ──────────────────────────────────────────────────────────────── */}
      <nav
        className="fixed top-0 w-full z-40 flex items-center justify-between px-8 py-4"
        style={{
          background: "rgba(3,13,26,0.88)",
          backdropFilter: "blur(14px)",
          borderBottom: "1px solid rgba(0,255,200,0.06)",
        }}
      >
        <div className="flex items-center gap-3">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: "#00ffcc", boxShadow: "0 0 8px #00ffcc", animation: "pulse-dot 2s ease-in-out infinite" }}
          />
          <span className="orb text-xs font-bold tracking-[0.22em]" style={{ color: "#00ffcc" }}>
            STOCKSENSE AI
          </span>
        </div>
        <div className="flex items-center gap-8">
          <a href="#steps" className="mono text-xs tracking-widest opacity-40 hover:opacity-100 transition-opacity" style={{ color: "#c8e0f4" }}>STEPS</a>
          <a href="#features" className="mono text-xs tracking-widest opacity-40 hover:opacity-100 transition-opacity" style={{ color: "#c8e0f4" }}>FEATURES</a>
          <Link
            href="/dashboard"
            className="orb primary-btn text-xs font-bold px-5 py-2 rounded tracking-[0.12em]"
          >
            DASHBOARD →
          </Link>
        </div>
      </nav>

      {/* ── HERO ─────────────────────────────────────────────────────────────── */}
      <section className="relative min-h-screen flex items-center pt-20">
        {/* corner brackets */}
        <div className="absolute top-28 left-8"><div className="corner-tl"/></div>
        <div className="absolute top-28 right-8"><div className="corner-tr"/></div>
        <div className="absolute bottom-16 left-8"><div className="corner-bl"/></div>
        <div className="absolute bottom-16 right-8"><div className="corner-br"/></div>

        <div className="max-w-7xl mx-auto px-8 w-full grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          {/* LEFT copy */}
          <div>
            {mounted && (
              <>
                <div className="fade-1 inline-flex items-center gap-2 px-3 py-1.5 rounded-sm mb-8"
                  style={{ background: "rgba(0,255,200,0.06)", border: "1px solid rgba(0,255,200,0.18)", color: "#00ffcc" }}>
                  <span className="w-1.5 h-1.5 rounded-full bg-current" style={{ animation: "pulse-dot 1.5s ease-in-out infinite" }} />
                  <span className="mono text-xs tracking-[0.25em]">LSTM + XGBOOST ENSEMBLE</span>
                </div>

                <h1
                  className="fade-2 orb font-black leading-none mb-8"
                  style={{ fontSize: "clamp(3.2rem, 6.5vw, 5.8rem)", letterSpacing: "-0.03em" }}
                >
                  <span style={{ color: "#00ffcc", textShadow: "0 0 40px rgba(0,255,200,0.35)" }}>PREDICT.</span><br />
                  <span style={{ color: "#0099ff" }}>ANALYZE.</span><br />
                  <span style={{ color: "#e2f0ff" }}>PROFIT.</span>
                </h1>

                <p className="fade-3 mono text-sm leading-loose mb-10 max-w-md"
                  style={{ color: "#4a7090", letterSpacing: "0.04em", lineHeight: "1.9" }}>
                  Production-grade ML stock intelligence — real LSTM sequences, XGBoost classification,
                  Redis-cached signals, WebSocket price feeds, JWT auth, and full Docker deployment.
                </p>

                <div className="fade-4 flex flex-wrap gap-4">
                  <Link href="/dashboard" className="orb primary-btn font-bold px-8 py-3.5 rounded text-sm tracking-[0.1em]">
                    OPEN DASHBOARD
                  </Link>
                  <a href="#steps" className="orb secondary-btn font-medium px-8 py-3.5 rounded text-sm tracking-[0.1em]">
                    DEPLOY GUIDE ↓
                  </a>
                </div>

                <div className="mt-12 mono text-xs flex items-center gap-2" style={{ color: "#1a3a5c" }}>
                  <span style={{ color: "#00ffcc" }}>›_</span>
                  <span>API running on :8000</span>
                  <span style={{ animation: "blink 1s step-end infinite", color: "#00ffcc" }}>█</span>
                </div>
              </>
            )}
          </div>

          {/* RIGHT — 3D neural net */}
          <div className="relative flex items-center justify-center">
            {/* outer halo rings */}
            <div className="absolute rounded-full pointer-events-none"
              style={{ width: 440, height: 440, border: "1px solid rgba(0,255,200,0.05)", top: "50%", left: "50%", transform: "translate(-50%,-50%)" }} />
            <div className="absolute rounded-full pointer-events-none"
              style={{ width: 340, height: 340, border: "1px solid rgba(0,153,255,0.07)", top: "50%", left: "50%", transform: "translate(-50%,-50%)" }} />

            {mounted && <NeuralNet3D />}

            {/* layer labels */}
            <div className="absolute bottom-2 left-0 right-0 flex justify-around px-10 pointer-events-none">
              {["INPUT", "LSTM", "XGB", "OUTPUT"].map((l, i) => (
                <span
                  key={l}
                  className="mono"
                  style={{ fontSize: 9, letterSpacing: "0.2em", color: LAYER_COLORS[i], opacity: 0.35 }}
                >
                  {l}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* scroll cue */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-25">
          <span className="mono" style={{ fontSize: 9, letterSpacing: "0.3em", color: "#00ffcc" }}>SCROLL</span>
          <div className="w-px h-8" style={{ background: "linear-gradient(to bottom, #00ffcc, transparent)" }} />
        </div>
      </section>

      {/* ── STATS BAR ─────────────────────────────────────────────────────────── */}
      <div style={{ borderTop: "1px solid rgba(0,255,200,0.07)", borderBottom: "1px solid rgba(0,255,200,0.07)" }}>
        <div className="max-w-7xl mx-auto px-8 py-5 flex flex-wrap gap-0">
          {STATS.map(({ label, value }, i) => (
            <div
              key={label}
              className="px-8 first:pl-0"
              style={{ borderRight: i < STATS.length - 1 ? "1px solid rgba(0,255,200,0.07)" : "none" }}
            >
              <div className="mono mb-1" style={{ fontSize: 9, color: "#1e4060", letterSpacing: "0.2em" }}>{label.toUpperCase()}</div>
              <div className="orb text-sm font-bold" style={{ color: "#00ffcc" }}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── NEXT STEPS TO GO LIVE ────────────────────────────────────────────── */}
      <section id="steps" className="py-32">
        <div className="max-w-5xl mx-auto px-8">
          {/* heading */}
          <div className="mb-16">
            <div className="mono text-xs tracking-[0.3em] mb-5" style={{ color: "#0099ff" }}>// DEPLOYMENT GUIDE</div>
            <h2 className="orb font-black leading-tight" style={{ fontSize: "clamp(2.4rem,5vw,3.8rem)", color: "#e2f0ff", letterSpacing: "-0.01em" }}>
              GO LIVE IN<br />
              <span style={{ color: "#00ffcc", textShadow: "0 0 30px rgba(0,255,200,0.3)" }}>4 COMMANDS.</span>
            </h2>
          </div>

          {/* terminal window */}
          <div
            className="rounded-lg overflow-hidden"
            style={{
              background: "rgba(1,7,17,0.96)",
              border: "1px solid rgba(0,255,200,0.1)",
              boxShadow: "0 40px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(0,255,200,0.04)",
            }}
          >
            {/* title bar */}
            <div
              className="flex items-center gap-2 px-5 py-3.5"
              style={{ background: "rgba(0,255,200,0.03)", borderBottom: "1px solid rgba(0,255,200,0.07)" }}
            >
              <span className="w-3 h-3 rounded-full" style={{ background: "#ff5f57" }} />
              <span className="w-3 h-3 rounded-full" style={{ background: "#febc2e" }} />
              <span className="w-3 h-3 rounded-full" style={{ background: "#28c840" }} />
              <span className="mono ml-4 text-xs tracking-widest" style={{ color: "rgba(0,255,200,0.25)", fontSize: 10 }}>
                stocksense — deployment.sh
              </span>
            </div>

            {/* steps */}
            {STEPS.map((s, i) => (
              <div key={i} className="step-row px-8 py-7 grid grid-cols-12 gap-6 items-start">
                {/* number */}
                <div className="col-span-1">
                  <span className="orb font-black text-2xl" style={{ color: "rgba(0,255,200,0.15)", lineHeight: 1 }}>
                    {s.num}
                  </span>
                </div>

                {/* content */}
                <div className="col-span-11">
                  {/* command */}
                  <div className="flex flex-wrap items-start gap-x-3 gap-y-1 mb-3">
                    <span className="mono text-xs pt-0.5 shrink-0" style={{ color: "rgba(0,255,200,0.4)" }}>
                      {s.prefix}
                    </span>
                    <code
                      className="mono text-sm font-bold"
                      style={{ color: "#00ffcc", whiteSpace: "pre", textShadow: "0 0 12px rgba(0,255,200,0.4)" }}
                    >
                      {s.cmd}
                    </code>
                  </div>
                  {/* description */}
                  <p className="mono text-xs leading-loose mb-4" style={{ color: "#3a6080", letterSpacing: "0.03em", lineHeight: "1.8" }}>
                    {s.desc}
                  </p>
                  {/* tag */}
                  <span
                    className="mono text-xs px-2.5 py-1 rounded-sm tracking-[0.15em]"
                    style={{ color: s.tagColor, background: `${s.tagColor}10`, border: `1px solid ${s.tagColor}28` }}
                  >
                    {s.tag}
                  </span>
                </div>
              </div>
            ))}

            {/* footer prompt */}
            <div
              className="px-8 py-4 mono text-xs"
              style={{ borderTop: "1px solid rgba(0,255,200,0.06)", color: "rgba(0,255,200,0.18)" }}
            >
              <span style={{ color: "rgba(0,255,200,0.4)" }}>$</span>
              {" "}system ready · stocksense-ai v1.0.0
              <span style={{ animation: "blink 1s step-end infinite", marginLeft: 4 }}>█</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── FEATURES ──────────────────────────────────────────────────────────── */}
      <section id="features" className="py-8 pb-32">
        <div className="max-w-6xl mx-auto px-8">
          <div className="mb-16">
            <div className="mono text-xs tracking-[0.3em] mb-5" style={{ color: "#0099ff" }}>// CAPABILITIES</div>
            <h2 className="orb font-black leading-tight" style={{ fontSize: "clamp(2.4rem,5vw,3.8rem)", color: "#e2f0ff", letterSpacing: "-0.01em" }}>
              WHAT&apos;S INSIDE<br />
              <span style={{ color: "#0099ff" }}>THE STACK.</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {FEATURES.map((f, i) => (
              <div key={i} className="feat-card rounded-lg p-7">
                <div
                  className="orb text-xl font-black mb-5"
                  style={{ color: f.col, textShadow: `0 0 14px ${f.col}55` }}
                >
                  {f.icon}
                </div>
                <h3 className="orb text-xs font-bold mb-3 leading-snug tracking-[0.08em]" style={{ color: f.col }}>
                  {f.title}
                </h3>
                <p className="mono text-xs leading-loose" style={{ color: "#3a6080", lineHeight: "1.85" }}>
                  {f.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────────────────────────── */}
      <section className="py-28 relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: "radial-gradient(ellipse at 50% 0%, rgba(0,255,200,0.05) 0%, transparent 65%)" }}
        />
        {/* horizontal rule top */}
        <div style={{ borderTop: "1px solid rgba(0,255,200,0.07)" }} className="absolute top-0 inset-x-0" />

        <div className="relative max-w-3xl mx-auto px-8 text-center">
          <div className="mono text-xs tracking-[0.3em] mb-6" style={{ color: "rgba(0,255,200,0.4)" }}>
            // READY TO SHIP
          </div>
          <h2
            className="orb font-black mb-6 leading-none"
            style={{
              fontSize: "clamp(2.8rem,6vw,5rem)",
              color: "#00ffcc",
              textShadow: "0 0 50px rgba(0,255,200,0.25), 0 0 100px rgba(0,255,200,0.1)",
              letterSpacing: "-0.02em",
            }}
          >
            PREDICT<br />MARKETS.
          </h2>
          <p className="mono text-sm mb-12" style={{ color: "#2a5070", letterSpacing: "0.08em", lineHeight: "2" }}>
            Train your first model and receive AI signals in minutes.
          </p>
          <Link
            href="/dashboard"
            className="orb primary-btn font-bold px-14 py-4 rounded text-sm inline-block tracking-[0.15em]"
          >
            OPEN DASHBOARD →
          </Link>
        </div>
      </section>

      {/* ── FOOTER ────────────────────────────────────────────────────────────── */}
      <footer
        className="py-7"
        style={{ borderTop: "1px solid rgba(0,255,200,0.05)" }}
      >
        <div className="max-w-7xl mx-auto px-8 flex items-center justify-between flex-wrap gap-4">
          <span className="orb text-xs font-bold tracking-[0.2em]" style={{ color: "rgba(0,255,200,0.25)" }}>
            STOCKSENSE AI
          </span>
          <span className="mono text-xs" style={{ color: "#0e2035" }}>
            FastAPI · PyTorch · XGBoost · Next.js · Redis · PostgreSQL · Docker
          </span>
        </div>
      </footer>
    </div>
  );
}
