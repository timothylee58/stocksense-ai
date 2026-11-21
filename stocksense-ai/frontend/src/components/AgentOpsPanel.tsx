"use client";

import React, { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const C = {
  panel: "#FFFFFF",
  line: "#E6E2D9",
  ink: "#17191E",
  muted: "#6E7075",
  faint: "#9C978D",
  accent: "#1F5E46",
  accentSoft: "#E9F1EC",
  danger: "#A33A31",
  dangerSoft: "#F9EBE8",
  warn: "#8A6430",
  warnSoft: "#F7EFE1",
};

type RunRow = {
  run_id: string;
  phase: string;
  status: string;
  recorded_at: string;
  strategy_version: string;
};

type Reconciliation = {
  ok: boolean;
  matched: number;
  ledger_executions: number;
  broker_orders: number;
  breaks: string[];
  checked_at: string;
};

type JournalVerify = { hash_chain_ok: boolean; breaks: string[] };

const STATUS_COLOR: Record<string, string> = {
  completed: C.accent,
  running: C.warn,
  halted: C.danger,
  aborted: C.danger,
};

function Chip({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  const color = ok ? C.accent : C.danger;
  return (
    <div
      className="flex items-center gap-2 rounded-xl px-3 py-2"
      style={{ background: ok ? C.accentSoft : C.dangerSoft, border: `1px solid ${C.line}` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      <span className="mono text-[10px] uppercase tracking-[0.08em]" style={{ color }}>
        {label}
      </span>
      {detail && (
        <span className="mono text-[10px]" style={{ color: C.muted }}>
          {detail}
        </span>
      )}
    </div>
  );
}

export default function AgentOpsPanel() {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [recon, setRecon] = useState<Reconciliation | null>(null);
  const [chain, setChain] = useState<JournalVerify | null>(null);
  const [reconUnavailable, setReconUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [runsRes, reconRes, chainRes] = await Promise.all([
          fetch(`${API_URL}/api/agents/runs?limit=5`),
          fetch(`${API_URL}/api/agents/reconciliation`),
          fetch(`${API_URL}/api/agents/journal/verify`),
        ]);
        if (!alive) return;
        if (!runsRes.ok || !chainRes.ok) {
          throw new Error(`agent API returned ${runsRes.status}/${chainRes.status}`);
        }
        const runsJson = await runsRes.json();
        const chainJson: JournalVerify = await chainRes.json();
        setRuns(runsJson.runs ?? []);
        setChain(chainJson);
        setReconUnavailable(!reconRes.ok);
        setRecon(reconRes.ok ? await reconRes.json() : null);
        setError(null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Agent operations unavailable");
      }
    };
    load();
    const timer = setInterval(load, 30_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const breaks = [...(recon?.breaks ?? []), ...(chain?.breaks ?? [])];

  return (
    <div className="card p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="serif text-[17px] font-semibold">Agent operations</h3>
          <p className="mt-1 text-[12px]" style={{ color: C.muted }}>
            Paper-only run loop · decisions ledgered · orders reconciled against the broker
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Chip
            label={recon?.ok ? "Reconciliation OK" : "Reconciliation break"}
            ok={!!recon?.ok}
            detail={
              recon
                ? `${recon.matched}/${recon.ledger_executions} matched`
                : reconUnavailable
                  ? "unavailable"
                  : undefined
            }
          />
          <Chip
            label={chain?.hash_chain_ok ? "Journal chain OK" : "Journal chain broken"}
            ok={!!chain?.hash_chain_ok}
            detail={chain ? `${chain.breaks.length} breaks` : undefined}
          />
        </div>
      </div>

      {error && (
        <div
          className="mb-4 rounded-lg px-3 py-2 text-[12px]"
          style={{ background: C.warnSoft, color: C.warn, border: `1px solid ${C.line}` }}
        >
          {error} — start the backend and run a shadow or paper session.
        </div>
      )}

      {runs.length === 0 && !error ? (
        <p className="text-[12px]" style={{ color: C.faint }}>
          No agent sessions yet. Run <span className="mono">POST /api/agents/run</span> with phase
          <span className="mono"> shadow</span> to populate the journal.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="mono text-[9px] uppercase tracking-[0.12em]" style={{ color: C.faint }}>
                <th className="pb-2 pr-4 font-normal">Session</th>
                <th className="pb-2 pr-4 font-normal">Phase</th>
                <th className="pb-2 pr-4 font-normal">Status</th>
                <th className="pb-2 pr-4 font-normal">Strategy</th>
                <th className="pb-2 font-normal">Finished</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id} className="border-t text-[12px]" style={{ borderColor: C.line }}>
                  <td className="mono py-2 pr-4" style={{ color: C.ink }}>
                    {run.run_id.replace(/^run-/, "")}
                  </td>
                  <td className="mono py-2 pr-4" style={{ color: C.muted }}>
                    {run.phase}
                  </td>
                  <td className="mono py-2 pr-4" style={{ color: STATUS_COLOR[run.status] ?? C.ink }}>
                    {run.status}
                  </td>
                  <td className="mono py-2 pr-4" style={{ color: C.muted }}>
                    {run.strategy_version}
                  </td>
                  <td className="mono py-2" style={{ color: C.faint }}>
                    {run.recorded_at ? run.recorded_at.replace("T", " ").slice(0, 19) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {breaks.length > 0 && (
        <ul className="mt-4 space-y-1">
          {breaks.map((b) => (
            <li key={b} className="mono text-[11px]" style={{ color: C.danger }}>
              • {b}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
