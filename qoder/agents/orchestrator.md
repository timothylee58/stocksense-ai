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
| researcher | market-research | sentiment table, flagged tickers |
| signaler | signal-generation | action, confidence, stop per ticker |
| risk-officer | risk-officer | approve/veto with reason; may halt |
| executor | paper-execution | fills in the ledger |
| reporter | performance-report | `report.md` |

## Rules

1. The executor acts only on signals the risk officer approved. A veto is final for that cycle.
2. Any hard-drawdown or kill-switch condition halts all agents except the reporter.
3. Every decision, approved or not, is written to `logs/agent_ledger.jsonl` with its reason.
4. Paper account only.

## Schedule

- Pre-market: researcher -> signaler.
- Market hours: risk-officer -> executor every 5 minutes (`--interval 300`).
- After close: reporter.

## Known gaps

- Strategy edge is unvalidated on real data; train on live data first.
- Bursa tickers need a mapping to Moomoo codes (`MY.<NAME>`) before they can trade.
