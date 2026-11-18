"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion, useScroll, useSpring } from "framer-motion";
import {
  Activity, ArrowRight, Boxes, BrainCircuit, Database, Lock, Radio,
} from "lucide-react";

// ─── Mercury palette ─────────────────────────────────────────────────────────
const C = {
  bg: "#F6F4EF",
  panel: "#FFFFFF",
  line: "#E6E2D9",
  lineStrong: "#D8D3C8",
  ink: "#17191E",
  inkSoft: "#3C3E44",
  muted: "#6E7075",
  faint: "#9C978D",
  accent: "#1F5E46",
  accentSoft: "#E9F1EC",
  danger: "#A33A31",
  warn: "#8A6430",
  info: "#4251A8",
  plum: "#6B5CA5",
};

const EASE = [0.22, 1, 0.36, 1] as const;

// ─── 3D Neural Network ────────────────────────────────────────────────────────
// Pure math: rotates nodes in 3D, projects to 2D with perspective. No libraries.

const LAYERS = [4, 6, 6, 2];
const LAYER_COLORS = [C.accent, C.inkSoft, C.muted, C.danger];
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
    const tick = () => { a += 0.0045; setAngle(a); id = requestAnimationFrame(tick); };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, []);

  const pts: Projected[] = useMemo(() => NET_NODES.map((n) => projectPt(n, angle)), [angle]);

  const sortedEdges = useMemo(
    () => [...NET_EDGES].sort((a, b) => {
      const da = (pts[a[0]].depth + pts[a[1]].depth) / 2;
      const db = (pts[b[0]].depth + pts[b[1]].depth) / 2;
      return da - db;
    }),
    [pts]
  );

  return (
    <svg width={SVG_W} height={SVG_H} aria-label="3D neural network visualization" style={{ maxWidth: "100%" }}>
      <defs>
        <radialGradient id="bg-halo" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={C.accent} stopOpacity="0.07" />
          <stop offset="100%" stopColor={C.accent} stopOpacity="0" />
        </radialGradient>
      </defs>

      <ellipse cx={SVG_W / 2} cy={SVG_H / 2} rx={240} ry={180} fill="url(#bg-halo)" />

      {sortedEdges.map(([a, b], i) => {
        const pa = pts[a], pb = pts[b];
        const d = (pa.depth + pb.depth) / 2;
        const op = Math.max(0.03, Math.min(0.26, (d + 360) / 750));
        return (
          <line key={i}
            x1={pa.px} y1={pa.py} x2={pb.px} y2={pb.py}
            stroke={LAYER_COLORS[pa.layer]} strokeWidth={0.6} strokeOpacity={op}
          />
        );
      })}

      {pts.map((p, i) => {
        const col = LAYER_COLORS[p.layer];
        const r = Math.max(2.6, 6.6 * p.scale);
        const op = Math.max(0.28, Math.min(0.95, (p.depth + 400) / 620));
        return (
          <g key={i} opacity={op}>
            <circle cx={p.px} cy={p.py} r={r * 2.6} fill={col} fillOpacity={0.07} />
            <circle cx={p.px} cy={p.py} r={r} fill={col} />
          </g>
        );
      })}
    </svg>
  );
}

// ─── Motion helpers ───────────────────────────────────────────────────────────

function Reveal({
  children, delay = 0, className,
}: {
  children: React.ReactNode; delay?: number; className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.7, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

// ─── Page Data ────────────────────────────────────────────────────────────────

const STEPS = [
  {
    num: "01",
    tag: "Model training",
    prefix: "curl -X POST localhost:8000",
    cmd: "/api/train/AAPL",
    desc: "Train your first LSTM + XGBoost ensemble on two years of daily AAPL data. Artefacts are versioned by timestamp and aliased as latest.",
  },
  {
    num: "02",
    tag: "Local dev",
    prefix: "$",
    cmd: "docker compose up",
    desc: "Boot the full stack in one command — FastAPI, Next.js, Redis, and PostgreSQL wired together with shared volumes.",
  },
  {
    num: "03",
    tag: "CI / CD",
    prefix: "$",
    cmd: "git push origin main",
    desc: "GitHub Actions runs backend lint, TypeScript checks, the Next.js build, and Docker image builds for both services.",
  },
  {
    num: "04",
    tag: "Auto-deploy",
    prefix: "github secrets →",
    cmd: "AWS_ACCESS_KEY_ID  ·  AWS_SECRET_ACCESS_KEY\nAMPLIFY_APP_ID  ·  APP_RUNNER_SERVICE_ARN",
    desc: "Add four repository secrets. Every merge to main deploys the frontend to AWS Amplify and the backend image to ECR, then App Runner.",
  },
];

const FEATURES = [
  { icon: BrainCircuit, accent: C.accent, tint: C.accentSoft, title: "LSTM + XGBoost ensemble", desc: "60% LSTM weight, 40% XGBoost. Falls back to a rule-based signal when no model artefact exists." },
  { icon: Radio, accent: C.info, tint: "#ECEEF9", title: "WebSocket live prices", desc: "Real-time streaming over /ws/ticker. Sixty-second intervals in session, five minutes off-hours." },
  { icon: Database, accent: C.warn, tint: "#F7EFE1", title: "Redis caching", desc: "Datasets cached for 15 minutes, predictions for 5. Turns a multi-second request into roughly 50 ms on a hit." },
  { icon: Activity, accent: C.accent, tint: C.accentSoft, title: "Technical indicators", desc: "RSI-14, MACD-12/26/9, and SMA-20/50 computed from two years of daily OHLCV history." },
  { icon: Lock, accent: C.plum, tint: "#F0EDF7", title: "JWT authentication", desc: "HMAC-SHA256 signed tokens with 24-hour expiry and salted password hashing. Register and login endpoints ready." },
  { icon: Boxes, accent: C.info, tint: "#ECEEF9", title: "Full DevOps stack", desc: "Docker Compose, multi-stage Dockerfiles, and GitHub Actions with lint, type-check, and image builds." },
];

const STATS = [
  { label: "Models", value: "LSTM + XGB" },
  { label: "Ensemble", value: "60 / 40" },
  { label: "Cache TTL", value: "15 / 5 min" },
  { label: "API routes", value: "12 endpoints" },
  { label: "Data window", value: "2yr daily" },
  { label: "Deploy", value: "Amplify + App Runner" },
];

// ─── Landing Page ─────────────────────────────────────────────────────────────

export default function LandingPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 160, damping: 26, mass: 0.4 });

  return (
    <div className="min-h-screen overflow-x-hidden" style={{ background: C.bg, color: C.ink }}>
      <motion.div
        className="fixed inset-x-0 top-0 z-[60] h-[2px] origin-left"
        style={{ scaleX: progress, background: C.accent }}
      />

      {/* ── NAV ──────────────────────────────────────────────────────────────── */}
      <nav
        className="fixed inset-x-0 top-0 z-50 flex items-center justify-between px-6 py-4 md:px-10"
        style={{
          background: "rgba(246, 244, 239, 0.86)",
          backdropFilter: "blur(16px)",
          borderBottom: `1px solid ${C.line}`,
        }}
      >
        <Link href="/" className="flex items-center gap-2.5">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: C.accent }} />
          <span className="serif text-[17px] font-semibold tracking-tight">StockSense</span>
          <span className="mono text-[9px] uppercase tracking-[0.22em]" style={{ color: C.faint }}>AI</span>
        </Link>
        <div className="flex items-center gap-3 md:gap-6">
          <a href="#steps" className="mono hidden text-[11px] uppercase tracking-[0.14em] transition-colors hover:opacity-60 sm:block" style={{ color: C.muted }}>
            Deployment
          </a>
          <a href="#features" className="mono hidden text-[11px] uppercase tracking-[0.14em] transition-colors hover:opacity-60 sm:block" style={{ color: C.muted }}>
            Capabilities
          </a>
          <Link
            href="/dashboard"
            className="mono inline-flex items-center gap-2 rounded-full px-4 py-2 text-[11px] uppercase tracking-[0.1em] transition-colors"
            style={{ background: C.ink, color: C.bg }}
          >
            Dashboard <ArrowRight size={12} />
          </Link>
        </div>
      </nav>

      {/* ── HERO ─────────────────────────────────────────────────────────────── */}
      <section className="relative flex min-h-screen items-center pt-28">
        <div className="mx-auto grid w-full max-w-7xl grid-cols-1 items-center gap-16 px-6 md:px-10 lg:grid-cols-2">
          <div>
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: EASE }}
              className="mb-8 inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5"
              style={{ borderColor: C.line, background: C.panel }}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: C.accent }} />
              <span className="mono text-[10px] uppercase tracking-[0.2em]" style={{ color: C.muted }}>
                LSTM · XGBoost · FinBERT
              </span>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 22 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.08, ease: EASE }}
              className="serif font-semibold leading-[0.98]"
              style={{ fontSize: "clamp(3rem, 6.4vw, 5.6rem)" }}
            >
              Predict.
              <br />
              <em style={{ color: C.accent }}>Analyze.</em>
              <br />
              Profit.
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.18, ease: EASE }}
              className="mt-8 max-w-md text-[15px] leading-relaxed"
              style={{ color: C.muted }}
            >
              Production-grade stock intelligence — real LSTM sequences, XGBoost classification,
              cached signals, live price feeds, and a paper-trading ledger you can audit.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.28, ease: EASE }}
              className="mt-10 flex flex-wrap items-center gap-3"
            >
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 rounded-full px-7 py-3.5 text-[13px] font-medium transition-colors"
                style={{ background: C.ink, color: C.bg }}
              >
                Open dashboard <ArrowRight size={14} />
              </Link>
              <a
                href="#steps"
                className="inline-flex items-center gap-2 rounded-full border px-7 py-3.5 text-[13px] font-medium transition-colors hover:bg-white"
                style={{ borderColor: C.lineStrong, color: C.inkSoft }}
              >
                Deployment guide
              </a>
            </motion.div>

            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 1, delay: 0.5 }}
              className="mono mt-12 flex items-center gap-2 text-[10px] uppercase tracking-[0.16em]"
              style={{ color: C.faint }}
            >
              <span className="h-1.5 w-1.5 animate-pulse rounded-full" style={{ background: C.accent }} />
              Paper account · API :8000
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1.1, delay: 0.15, ease: EASE }}
            className="relative flex items-center justify-center"
          >
            <div className="pointer-events-none absolute h-[440px] w-[440px] rounded-full border" style={{ borderColor: C.line }} />
            <div className="pointer-events-none absolute h-[330px] w-[330px] rounded-full border" style={{ borderColor: C.line }} />
            {mounted && <NeuralNet3D />}

            <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-around px-10">
              {["INPUT", "LSTM", "XGB", "OUTPUT"].map((l, i) => (
                <span key={l} className="mono text-[9px] uppercase tracking-[0.22em]" style={{ color: LAYER_COLORS[i], opacity: 0.6 }}>
                  {l}
                </span>
              ))}
            </div>
          </motion.div>
        </div>

        <div className="absolute bottom-8 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2">
          <span className="mono text-[9px] uppercase tracking-[0.3em]" style={{ color: C.faint }}>Scroll</span>
          <div className="h-9 w-px" style={{ background: `linear-gradient(to bottom, ${C.lineStrong}, transparent)` }} />
        </div>
      </section>

      {/* ── STATS BAR ─────────────────────────────────────────────────────────── */}
      <div style={{ borderTop: `1px solid ${C.line}`, borderBottom: `1px solid ${C.line}` }}>
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-y-5 px-6 py-6 sm:grid-cols-3 md:px-10 lg:grid-cols-6">
          {STATS.map(({ label, value }, i) => (
            <div key={label} className="px-5 first:pl-0" style={{ borderLeft: i === 0 ? "none" : `1px solid ${C.line}` }}>
              <div className="eyebrow mb-1.5">{label}</div>
              <div className="serif text-[18px] font-semibold" style={{ color: C.ink }}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── DEPLOYMENT ────────────────────────────────────────────────────────── */}
      <section id="steps" className="scroll-mt-24 py-28">
        <div className="mx-auto max-w-5xl px-6 md:px-10">
          <Reveal>
            <div className="eyebrow mb-4">Deployment</div>
            <h2 className="serif text-[clamp(2.2rem,4.6vw,3.4rem)] font-semibold leading-[1.05]">
              Live in four <em style={{ color: C.accent }}>commands.</em>
            </h2>
          </Reveal>

          <Reveal delay={0.12}>
            <div className="mt-14 overflow-hidden rounded-2xl border bg-white" style={{ borderColor: C.line }}>
              <div className="flex items-center gap-2 border-b px-6 py-3.5" style={{ borderColor: C.line }}>
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: C.lineStrong }} />
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: C.lineStrong }} />
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: C.lineStrong }} />
                <span className="mono ml-3 text-[10px] tracking-[0.12em]" style={{ color: C.faint }}>
                  stocksense — deployment.sh
                </span>
              </div>

              {STEPS.map((s, i) => (
                <div
                  key={s.num}
                  className="group grid grid-cols-[40px_1fr] gap-5 px-6 py-8 transition-colors hover:bg-[#FBFAF6] md:grid-cols-[56px_1fr] md:px-8"
                  style={{ borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}
                >
                  <span className="serif text-2xl font-semibold" style={{ color: C.lineStrong, lineHeight: 1 }}>
                    {s.num}
                  </span>
                  <div>
                    <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="mono text-[11px]" style={{ color: C.faint }}>{s.prefix}</span>
                      <code className="mono whitespace-pre-wrap text-[12.5px] font-bold" style={{ color: C.ink }}>
                        {s.cmd}
                      </code>
                    </div>
                    <p className="mb-4 max-w-xl text-[13.5px] leading-relaxed" style={{ color: C.muted }}>
                      {s.desc}
                    </p>
                    <span
                      className="mono inline-flex rounded-full border px-2.5 py-1 text-[9px] uppercase tracking-[0.14em]"
                      style={{ borderColor: C.line, color: C.inkSoft, background: C.bg }}
                    >
                      {s.tag}
                    </span>
                  </div>
                </div>
              ))}

              <div className="mono flex items-center gap-2 border-t px-6 py-4 text-[10px] tracking-[0.12em]" style={{ borderColor: C.line, color: C.faint }}>
                <span style={{ color: C.accent }}>$</span>
                <span>system ready · stocksense-ai v1.0.0</span>
                <span className="animate-pulse">█</span>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── FEATURES ──────────────────────────────────────────────────────────── */}
      <section id="features" className="scroll-mt-24 pb-28">
        <div className="mx-auto max-w-6xl px-6 md:px-10">
          <Reveal>
            <div className="eyebrow mb-4">Capabilities</div>
            <h2 className="serif text-[clamp(2.2rem,4.6vw,3.4rem)] font-semibold leading-[1.05]">
              Inside <em style={{ color: C.accent }}>the stack.</em>
            </h2>
          </Reveal>

          <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, i) => {
              const Icon = f.icon;
              return (
                <Reveal key={f.title} delay={i * 0.05}>
                  <div
                    className="group h-full rounded-2xl border bg-white p-7 transition-all duration-300 hover:-translate-y-1"
                    style={{ borderColor: C.line, boxShadow: "0 1px 2px rgba(23,25,30,0.03)" }}
                  >
                    <div className="mb-6 flex h-9 w-9 items-center justify-center rounded-full" style={{ background: f.tint }}>
                      <Icon size={16} style={{ color: f.accent }} />
                    </div>
                    <h3 className="serif mb-2.5 text-[16px] font-semibold">{f.title}</h3>
                    <p className="text-[13px] leading-relaxed" style={{ color: C.muted }}>{f.desc}</p>
                  </div>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────────────────────────── */}
      <section className="pb-28">
        <div className="mx-auto max-w-5xl px-6 md:px-10">
          <Reveal>
            <div
              className="paper-grid relative overflow-hidden rounded-3xl border px-8 py-16 text-center md:py-20"
              style={{ borderColor: C.line, background: C.panel }}
            >
              <div
                className="pointer-events-none absolute inset-0"
                style={{ background: `radial-gradient(ellipse at 50% 0%, ${C.accentSoft} 0%, transparent 62%)` }}
              />
              <div className="relative">
                <div className="eyebrow mb-5">Ready to ship</div>
                <h2 className="serif text-[clamp(2.4rem,5vw,4rem)] font-semibold leading-[1.02]">
                  Read the signal,
                  <br />
                  <em style={{ color: C.accent }}>not the noise.</em>
                </h2>
                <p className="mx-auto mt-6 max-w-md text-[14px] leading-relaxed" style={{ color: C.muted }}>
                  Train your first model, then open the dashboard for forecasts, timing, and a paper-trading ledger.
                </p>
                <Link
                  href="/dashboard"
                  className="mt-10 inline-flex items-center gap-2 rounded-full px-10 py-4 text-[13px] font-medium"
                  style={{ background: C.ink, color: C.bg }}
                >
                  Open dashboard <ArrowRight size={14} />
                </Link>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── FOOTER ────────────────────────────────────────────────────────────── */}
      <footer style={{ borderTop: `1px solid ${C.line}` }}>
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-8 md:px-10">
          <div className="flex items-center gap-2.5">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: C.accent }} />
            <span className="serif text-[14px] font-semibold">StockSense AI</span>
          </div>
          <span className="mono text-[10px] tracking-[0.08em]" style={{ color: C.faint }}>
            FastAPI · PyTorch · XGBoost · Next.js · Redis · PostgreSQL · Docker
          </span>
        </div>
      </footer>
    </div>
  );
}
