"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import {
  Activity, AlertTriangle, BarChart3, Clock, RefreshCw,
  ShieldAlert, TrendingDown, TrendingUp, Wallet, XCircle,
} from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Summary = {
  demo: boolean;
  generated_at: string;
  account: {
    verified?: boolean;
    source?: string;
    trd_env?: string;
    account_id?: string;
    currency?: string;
  };
  summary: {
    equity: number;
    cash: number;
    market_value: number;
    day_pnl: number;
    day_pnl_pct: number;
    baseline_equity: number;
    total_pnl: number;
    total_return_pct: number;
    gross_exposure_pct: number;
    position_count: number;
    kill_switch_active: boolean;
    snapshot_storage: string;
  };
  positions: Array<{
    ticker: string;
    quantity: number;
    market_value: number;
    allocation_pct: number;
  }>;
  kill_switch: { enabled: boolean; reason: string; actor: string; updated_at: string | null };
  ledger: {
    total_events: number;
    decisions: number;
    approved: number;
    rejected: number;
    executions: number;
    filled: number;
    dry_run: number;
    failed: number;
    duplicate_blocked: number;
  };
};

type CurvePoint = {
  snapshot_id: string;
  equity: number;
  cash: number;
  market_value: number;
  day_pnl: number;
  captured_at: string;
};

type Rejection = {
  decision_id: string;
  ticker: string;
  side: string;
  quantity: number;
  price: number;
  notional: number;
  reason_codes: string[];
  strategy_id: string;
  actor: string;
  event_time: string;
};

const GREEN = "#00ffcc";
const RED = "#ff4560";
const AMBER = "#f5a623";
const BLUE = "#0099ff";

function money(v: number) {
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function signedPct(v: number) {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function pnlColor(v: number) {
  if (v > 0) return GREEN;
  if (v < 0) return RED;
  return "#c8e0f4";
}

function clock(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "--:--"
    : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function chartLabel(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--";
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number | string }>;
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  const value = Number(payload[0]?.value ?? 0);
  return (
    <div className="mono text-xs rounded-md px-3 py-2"
      style={{ background: "#020a14", border: "1px solid rgba(0,255,200,0.25)", color: "#e2f0ff" }}>
      <div style={{ color: "#6a90b0" }}>{label}</div>
      <div style={{ color: GREEN }}>{money(value)}</div>
    </div>
  );
}

function MetricCard({
  label, value, sub, color, icon,
}: {
  label: string;
  value: string;
  sub: string;
  color: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="metric-card px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="mono text-[10px] tracking-widest" style={{ color: "#6a90b0" }}>{label}</span>
        <span style={{ color }}>{icon}</span>
      </div>
      <div className="orb text-xl font-bold mt-1" style={{ color }}>{value}</div>
      <div className="mono text-[10px] mt-0.5" style={{ color: "#5d7d99" }}>{sub}</div>
    </div>
  );
}

export default function OpsPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [curve, setCurve] = useState<CurvePoint[]>([]);
  const [rejections, setRejections] = useState<Rejection[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [summaryRes, curveRes, rejectedRes] = await Promise.all([
        fetch(`${API_URL}/api/portfolio/summary`, { cache: "no-store" }),
        fetch(`${API_URL}/api/portfolio/equity-curve?limit=500`, { cache: "no-store" }),
        fetch(`${API_URL}/api/portfolio/rejected?limit=25`, { cache: "no-store" }),
      ]);

      if (!summaryRes.ok) {
        const body = await summaryRes.json().catch(() => null);
        const detail = body?.detail;
        const message = typeof detail === "object" && detail !== null
          ? `${detail.code}: ${detail.message}`
          : detail ?? `API ${summaryRes.status}`;
        setError(message);
        setLoading(false);
        return;
      }

      const summaryBody: Summary = await summaryRes.json();
      const curveBody: { points: CurvePoint[] } = curveRes.ok
        ? await curveRes.json()
        : { points: [] };
      const rejectedBody: { rejections: Rejection[] } = rejectedRes.ok
        ? await rejectedRes.json()
        : { rejections: [] };

      setSummary(summaryBody);
      setCurve(curveBody.points);
      setRejections(rejectedBody.rejections);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reach the API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 30_000);
    return () => clearInterval(timer);
  }, [load]);

  const s = summary?.summary;
  const killActive = summary?.kill_switch.enabled ?? false;
  const equities = curve.map((p) => p.equity);
  const minEquity = equities.length ? Math.min(...equities) : 0;
  const maxEquity = equities.length ? Math.max(...equities) : 0;
  const yPad = Math.max((maxEquity - minEquity) * 0.25, maxEquity * 0.0015, 1);
  const yDomain: [number, number] = [minEquity - yPad, maxEquity + yPad];

  return (
    <div className="min-h-screen" style={{ background: "#030d1a", fontFamily: "Share Tech Mono, monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');
        .orb { font-family: 'Orbitron', monospace; }
        .mono { font-family: 'Share Tech Mono', monospace; }
        .card { background: rgba(0,12,28,0.8); border: 1px solid rgba(0,153,255,0.1); border-radius: 12px; }
        .metric-card { background: rgba(0,8,20,0.9); border: 1px solid rgba(0,255,200,0.08); border-radius: 10px; transition: border-color 0.3s; }
        .metric-card:hover { border-color: rgba(0,255,200,0.25); }
        .nav-btn { background: rgba(0,255,200,0.06); border: 1px solid rgba(0,255,200,0.3); color: #00ffcc; transition: all 0.2s; }
        .nav-btn:hover { background: rgba(0,255,200,0.12); }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(0,255,200,0.15); border-radius: 2px; }
      `}</style>

      <nav className="sticky top-0 z-40 flex items-center justify-between px-6 py-3"
        style={{ background: "rgba(3,13,26,0.92)", backdropFilter: "blur(14px)", borderBottom: "1px solid rgba(0,255,200,0.06)" }}>
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ background: GREEN, boxShadow: `0 0 8px ${GREEN}` }} />
            <span className="orb text-xs font-bold tracking-widest" style={{ color: GREEN }}>STOCKSENSE AI</span>
          </Link>
          <span className="mono text-xs opacity-20" style={{ color: "#c8e0f4" }}>/ ops</span>
          <div className="flex items-center gap-1 ml-2">
            <Link href="/dashboard" className="mono px-2 py-1 rounded"
              style={{ fontSize: 9, color: "#6a90b0", border: "1px solid rgba(255,255,255,0.06)" }}>
              DASHBOARD
            </Link>
            <Link href="/dashboard/sentiment" className="mono px-2 py-1 rounded"
              style={{ fontSize: 9, color: "#6a90b0", border: "1px solid rgba(255,255,255,0.06)" }}>
              SENTIMENT
            </Link>
            <Link href="/dashboard/anomalies" className="mono px-2 py-1 rounded"
              style={{ fontSize: 9, color: "#6a90b0", border: "1px solid rgba(255,255,255,0.06)" }}>
              ANOMALIES
            </Link>
            <span className="mono px-2 py-1 rounded flex items-center gap-1"
              style={{ fontSize: 9, color: GREEN, border: `1px solid ${GREEN}40`, background: `${GREEN}0f` }}>
              <ShieldAlert size={10} /> OPS
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="mono text-[10px]" style={{ color: killActive ? RED : "#6a90b0" }}>
            {killActive ? "KILL SWITCH ACTIVE" : "KILL SWITCH CLEAR"}
          </span>
          <button onClick={load} disabled={loading} className="nav-btn orb text-xs font-bold px-4 py-1.5 rounded">
            <RefreshCw size={12} className="inline mr-1.5" />{loading ? "LOADING" : "REFRESH"}
          </button>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="orb text-lg font-bold tracking-widest" style={{ color: "#e2f0ff" }}>
              EXECUTION CONTROL
            </h1>
            <p className="mono text-[11px] mt-1" style={{ color: "#6a90b0" }}>
              {summary
                ? `${summary.account.account_id ?? "unknown"} · ${summary.account.trd_env ?? "SIMULATE"} · ${summary.demo ? "DEMO MODE" : "PAPER"} · snapshot ${summary.summary.snapshot_storage}`
                : "Waiting for the account guard"}
            </p>
          </div>
          {summary && (
            <span className="mono text-[10px]" style={{ color: "#5d7d99" }}>
              <Clock size={10} className="inline mr-1" />
              refreshed {clock(summary.generated_at)} · auto 30s
            </span>
          )}
        </div>

        {error && (
          <div className="card px-4 py-3 flex items-start gap-3" style={{ borderColor: `${RED}55`, background: `${RED}0d` }}>
            <AlertTriangle size={16} style={{ color: RED, flexShrink: 0, marginTop: 2 }} />
            <div>
              <div className="mono text-xs" style={{ color: RED }}>ACCOUNT GUARD BLOCKED</div>
              <div className="mono text-[11px] mt-1" style={{ color: "#c8e0f4" }}>{error}</div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          <MetricCard label="EQUITY" value={s ? money(s.equity) : "—"} sub="account value"
            color="#e2f0ff" icon={<Wallet size={14} />} />
          <MetricCard label="CASH" value={s ? money(s.cash) : "—"} sub="available"
            color={BLUE} icon={<Wallet size={14} />} />
          <MetricCard label="DAY P&L" value={s ? `${money(s.day_pnl)} (${signedPct(s.day_pnl_pct)})` : "—"} sub="today"
            color={s ? pnlColor(s.day_pnl) : "#c8e0f4"}
            icon={s && s.day_pnl < 0 ? <TrendingDown size={14} /> : <TrendingUp size={14} />} />
          <MetricCard label="TOTAL P&L" value={s ? `${money(s.total_pnl)} (${signedPct(s.total_return_pct)})` : "—"} sub={s ? `baseline ${money(s.baseline_equity)}` : "since first snapshot"}
            color={s ? pnlColor(s.total_pnl) : "#c8e0f4"}
            icon={s && s.total_pnl < 0 ? <TrendingDown size={14} /> : <TrendingUp size={14} />} />
          <MetricCard label="EXPOSURE" value={s ? `${s.gross_exposure_pct.toFixed(2)}%` : "—"} sub={s ? `${s.position_count} positions · ${money(s.market_value)}` : "gross"}
            color={s && s.gross_exposure_pct > 90 ? AMBER : GREEN} icon={<BarChart3 size={14} />} />
          <MetricCard label="REJECTED" value={summary ? String(summary.ledger.rejected) : "—"} sub={summary ? `${summary.ledger.decisions} decisions · ${summary.ledger.filled} fills` : "ledger"}
            color={summary && summary.ledger.rejected > 0 ? AMBER : GREEN} icon={<XCircle size={14} />} />
        </div>

        <section className="card px-4 py-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Activity size={14} style={{ color: GREEN }} />
              <span className="orb text-xs font-bold tracking-widest" style={{ color: "#e2f0ff" }}>EQUITY CURVE</span>
            </div>
            <span className="mono text-[10px]" style={{ color: "#5d7d99" }}>
              {curve.length} snapshot{curve.length === 1 ? "" : "s"} · baseline {s ? money(s.baseline_equity) : "—"}
            </span>
          </div>
          <div style={{ height: 280 }}>
            {curve.length === 0 ? (
              <div className="h-full flex items-center justify-center mono text-xs" style={{ color: "#5d7d99" }}>
                No snapshots yet — the first summary read records one.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={curve} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="captured_at" tickFormatter={chartLabel}
                    tick={{ fill: "#5d7d99", fontSize: 9 }} axisLine={false} tickLine={false} minTickGap={32} />
                  <YAxis domain={yDomain} tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`}
                    tick={{ fill: "#5d7d99", fontSize: 9 }} axisLine={false} tickLine={false} width={54} />
                  <Tooltip content={<ChartTooltip />} />
                  {s && (
                    <ReferenceLine y={s.baseline_equity} stroke="rgba(245,166,35,0.45)" strokeDasharray="4 4" />
                  )}
                  <Line type="monotone" dataKey="equity" stroke={GREEN} strokeWidth={2} dot={false}
                    activeDot={{ r: 4, fill: GREEN }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <section className="card px-4 py-4">
            <div className="flex items-center justify-between mb-3">
              <span className="orb text-xs font-bold tracking-widest" style={{ color: "#e2f0ff" }}>OPEN POSITIONS</span>
              <span className="mono text-[10px]" style={{ color: "#5d7d99" }}>{summary?.positions.length ?? 0}</span>
            </div>
            {!summary || summary.positions.length === 0 ? (
              <div className="mono text-xs py-8 text-center" style={{ color: "#5d7d99" }}>Flat — no open positions.</div>
            ) : (
              <table className="w-full mono text-[11px]">
                <thead>
                  <tr style={{ color: "#5d7d99" }}>
                    <th className="text-left font-normal pb-2">TICKER</th>
                    <th className="text-right font-normal pb-2">QTY</th>
                    <th className="text-right font-normal pb-2">VALUE</th>
                    <th className="text-right font-normal pb-2">WEIGHT</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.positions.map((p) => (
                    <tr key={p.ticker} style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
                      <td className="py-2" style={{ color: GREEN }}>{p.ticker}</td>
                      <td className="py-2 text-right" style={{ color: "#c8e0f4" }}>{p.quantity.toLocaleString()}</td>
                      <td className="py-2 text-right" style={{ color: "#c8e0f4" }}>{money(p.market_value)}</td>
                      <td className="py-2 text-right" style={{ color: p.allocation_pct > 25 ? AMBER : "#c8e0f4" }}>
                        {p.allocation_pct.toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {summary && (
              <div className="mt-4 pt-3 grid grid-cols-4 gap-2" style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                {[
                  ["APPROVED", summary.ledger.approved, GREEN],
                  ["REJECTED", summary.ledger.rejected, AMBER],
                  ["FILLED", summary.ledger.filled, BLUE],
                  ["FAILED", summary.ledger.failed, RED],
                ].map(([label, value, color]) => (
                  <div key={String(label)}>
                    <div className="mono text-[9px]" style={{ color: "#5d7d99" }}>{label}</div>
                    <div className="orb text-sm font-bold" style={{ color: String(color) }}>{String(value)}</div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="card px-4 py-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <XCircle size={14} style={{ color: AMBER }} />
                <span className="orb text-xs font-bold tracking-widest" style={{ color: "#e2f0ff" }}>REJECTED ORDERS</span>
              </div>
              <span className="mono text-[10px]" style={{ color: "#5d7d99" }}>latest {rejections.length}</span>
            </div>
            {rejections.length === 0 ? (
              <div className="mono text-xs py-8 text-center" style={{ color: "#5d7d99" }}>
                No rejections recorded. Every blocked order appears here with its reason codes.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full mono text-[11px]">
                  <thead>
                    <tr style={{ color: "#5d7d99" }}>
                      <th className="text-left font-normal pb-2">TIME</th>
                      <th className="text-left font-normal pb-2">ORDER</th>
                      <th className="text-right font-normal pb-2">NOTIONAL</th>
                      <th className="text-left font-normal pb-2 pl-3">REASONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rejections.map((r) => (
                      <tr key={r.decision_id} style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
                        <td className="py-2" style={{ color: "#5d7d99" }}>{clock(r.event_time)}</td>
                        <td className="py-2" style={{ color: "#c8e0f4" }}>
                          <span style={{ color: r.side === "BUY" ? GREEN : RED }}>{r.side}</span>{" "}
                          {r.ticker} × {r.quantity}
                        </td>
                        <td className="py-2 text-right" style={{ color: "#c8e0f4" }}>{money(r.notional)}</td>
                        <td className="py-2 pl-3">
                          <div className="flex flex-wrap gap-1">
                            {r.reason_codes.map((code) => (
                              <span key={code} className="px-1.5 py-0.5 rounded"
                                style={{ fontSize: 9, color: AMBER, background: `${AMBER}14`, border: `1px solid ${AMBER}33` }}>
                                {code}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        {killActive && summary && (
          <div className="card px-4 py-3" style={{ borderColor: `${RED}44`, background: `${RED}0a` }}>
            <div className="mono text-[11px]" style={{ color: RED }}>
              KILL SWITCH ACTIVE — buys are blocked, sells remain allowed to flatten.
            </div>
            <div className="mono text-[10px] mt-1" style={{ color: "#c8e0f4" }}>
              {summary.kill_switch.reason || "no reason recorded"} · set by {summary.kill_switch.actor || "unknown"}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
