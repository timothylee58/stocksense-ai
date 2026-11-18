# Orchestrator (multi-agent spec)

Goal: run a risk-controlled paper-trading cycle on the Moomoo paper account and produce a
daily report.

## Agents and handoffs

```
researcher --sentiment--> signaler --signals--> risk-officer --approved orders--> executor
                                                     |                                |
                                                  veto/halt                        fills
                                                     v                                v
                                                  ledger  <---------------------- reporter
```

| Agent | Skill | Output |
|---|---|---|
| researcher | market-research | market-wide sentiment context (informational only) |
| signaler | signal-generation | action, confidence, stop per ticker |
| risk-officer | risk-officer | approve/veto with reason; may halt |
| executor | paper-execution | fills in the ledger |
| reporter | performance-report | `report.md` |

## Rules

1. The executor acts only on risk-approved *entry* signals; stop-loss and SELL exits execute immediately and are never blocked. A veto is final for that cycle's entries.
2. Any hard-drawdown or kill-switch condition blocks new entries and makes the executor flatten the book; the reporter still runs.
3. Every decision, approved or not, is written to `logs/agent_ledger.jsonl` with its reason.
4. Paper account only.

## Schedule

- Pre-market: researcher (market-wide context for the operator). Signals are generated inside each
  cycle by `predictor_source`; there is no separate pre-market signaler step.
- Market hours: risk-officer -> executor every 5 minutes. One process runs `--cycles N` cycles with `--interval 300` between them (without `--cycles`, it runs one cycle and exits); size `N` to the session length.
- After close: reporter.

## Known gaps

- Strategy edge is unvalidated on real data; train on live data first.
- Bursa tickers need a mapping to Moomoo codes (`MY.<NAME>`) before they can trade.
