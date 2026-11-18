# StockSense Agent: Product Requirements (Moomoo x Qoder AI Trading Agent Challenge)

Status: draft, written 2026-11-18. Source of the challenge terms: the Luma event page
(criteria are marked "subject to change"; the participation handbook has not been reviewed).

## 1. Goal

Turn StockSense AI's prediction engine into an autonomous, risk-controlled trading agent that
trades the Moomoo paper account (US$100k simulated) and is built and orchestrated with Qoder
and Qoder Cloud Agents.

Success = a complete submission by **30 Nov 2026, 23:59 SGT**, strong on the four judged areas,
with an honest record of what worked and what failed. Top 10 present on 8 Dec.

## 2. Challenge facts

| Item | Detail |
|---|---|
| Dev and trading window | 17-28 Nov 2026 |
| Submission | Qoder-generated deck + runnable trading-agent package: strategy explanation, risk limits, log of decisions, fills and results, demo of what worked, what failed, and why |
| Capital | Simulated, no live funds |
| Judging | Qoder & Cloud Agent usage 30%, Strategy & risk design 30%, Risk-adjusted return 25%, Reusability & documentation 15% |

## 3. Users

- **Judges:** need to see a clear thesis, enforced risk controls, real agent engineering in Qoder, and reproducible docs.
- **Operator (the entrant):** runs cycles, can halt the agent instantly, reads daily reports.

## 4. Scope

### In scope
1. Signal generation from the existing ensemble (`app/ml/predictor.py`).
2. Risk gate with hard limits, kill switch and strategy invalidation (`app/agent/risk.py`).
3. Execution loop and Moomoo paper broker (`app/agent/loop.py`, `moomoo_broker.py`).
4. Append-only decision/fill/equity ledger and report (`ledger.py`, `report.py`).
5. Qoder skills and a multi-agent orchestration spec (`qoder/`).
6. Submission deck and docs.

### Out of scope
- Live trading (the broker is hard-wired to simulate).
- Shorting, options, leverage.
- Bursa Malaysia trading unless the paper account supports it (unconfirmed).
- The StockSense web dashboard (kept as an optional demo surface only).

## 5. Strategy (draft hypothesis, unvalidated)

**Thesis.** Combine a technical-indicator model ensemble with sentiment as a filter, and take
long-only positions in liquid US names only when model confidence clears a threshold and every
risk check passes. The edge is expected to be small; the entry's differentiator is disciplined
risk control and a transparent audit trail rather than raw return.

**Entry:** signal BUY, confidence >= 0.60, risk gate approves.
**Exit:** SELL signal or stop-loss hit; forced flatten on kill switch or hard drawdown.

**Invalidation (strategy considered broken, new entries stop until a human reviews):**
- 5 consecutive losing trades, or
- hit rate < 35% over the last 20 closed trades.

**Risk limits (defaults, not yet tuned):** 0.5% equity risked per trade to the stop; 10% max per
position; 60% max gross exposure; 5 max positions; soft drawdown 5% (half size); hard drawdown
10% (halt + flatten); 3% daily loss limit.

## 6. Requirements

| ID | Requirement | Status |
|---|---|---|
| R1 | Agent never places a live order | Done (SIMULATE hard-coded) |
| R2 | Every decision logged with reason, including rejections | Done |
| R3 | Kill switch halts and flattens within one cycle | Done (tested with sim broker) |
| R4 | Position sizing from risk-to-stop, capped by limits | Done |
| R5 | Moomoo paper broker adapter | Written, **not tested against a real OpenD** |
| R6 | Signals come from a model that is actually trained and validated | **Open** (see section 8) |
| R7 | Qoder agents/skills built and run in Qoder Cloud Agents | **Open** (drafts only) |
| R8 | Daily report generated from ledger | Done (`app.agent.report`) |
| R9 | Real paper-trading record covering several trading days | **Open** |
| R10 | Deck + runnable package + demo | **Open** |

## 7. Mapping to judging criteria

| Criterion | Weight | Plan | Gap |
|---|---|---|---|
| Qoder & Cloud Agent usage | 30% | Build researcher, signaler, risk-officer, executor, reporter as Cloud Agents using the skills in `qoder/`; generate dashboards/reports and the deck in Qoder | Nothing built in Qoder yet |
| Strategy & risk design | 30% | Thesis, invalidation rules, limits, drawdown ladder, kill switch (all in code and tested) | Limits untuned; signal unvalidated |
| Risk-adjusted return | 25% | Run the loop daily on paper from as early as possible; report Sharpe/drawdown from real fills | No paper record yet; short window |
| Reusability & documentation | 15% | `qoder/` skills, `ARCHITECTURE.md`, this PRD, tests, Makefile/Docker | Needs a quickstart and the deck |

## 8. Known issues to fix (affect credibility)

1. **Two separate XGBoost pipelines.** The live predictor (`predict_xgb`) loads
   `models/<TICKER>_xgb.pkl`, a 3-class BUY/SELL/HOLD model (about +/-1.5% over 5 days) trained
   by `POST /api/train/<TICKER>`. The Optuna/SHAP/backtest pipeline (`scripts/train_model.py`)
   trains a *binary next-day UP/DOWN* model saved as `models/xgb_<TICKER>.json`, which is used by
   `/api/explain` and `/api/backtest` but **not** by `run_prediction`. So the backtest and SHAP
   currently describe a different model from the one that trades. Without the pickle, the
   predictor silently falls back to a rule-based RSI+MACD signal.
2. **Ensemble weights differ from the documented 50/30/20.** `run_prediction` uses 60% LSTM
   (7-day forecast direction) and 40% XGBoost, with no FinBERT; its `sentiment_score` is derived
   from RSI/MACD, not news. FinBERT currently feeds `ingest_news`/Supabase, not the signal.
3. **LSTM did not train in the demo run** (`"lstm": {}`); cause not diagnosed.
4. Demo-mode metrics are noise; no real-data validation exists yet.

Decision needed: either point the agent at the `train_model.py` binary model (so backtest, SHAP
and trading share one model) or retrain via the existing endpoint. The first is cleaner for the
story and the report.

## 9. Plan (today 18 Nov to 30 Nov)

| Dates | Work | Owner |
|---|---|---|
| 18-19 | Unify the signal model (fix section 8.1); train on live data; verify broker against OpenD (columns, security firm) | Claude + entrant |
| 19-20 | Start paper trading loop daily; tune limits from first fills | Entrant (needs OpenD) |
| 19-24 | Build the five agents in Qoder Cloud Agents from `qoder/` | Entrant (Qoder access) |
| 24-28 | Iterate on failures; add dashboard/report automation; collect "what failed and why" | Both |
| 28-29 | Generate deck in Qoder; record demo; write quickstart | Entrant + Claude |
| 30 | Final checks, submit before 23:59 SGT | Entrant |

## 10. Risks

| Risk | Mitigation |
|---|---|
| Too few trading days for a meaningful return score | Start paper trading as soon as the broker is verified |
| Signal has no edge | Lean on risk design and honest reporting; do not overclaim |
| Moomoo API mismatch breaks the adapter | Test against OpenD early; adapter is isolated behind `Broker` |
| Qoder usage under-delivered | Prioritise real multi-agent orchestration over polish |
| Market closed or illiquid when orders are sent | Fill timeout + cancel; log non-fills |
