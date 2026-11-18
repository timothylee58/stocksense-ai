# Qoder drafts for the Moomoo x Qoder challenge

Drafts of reusable skills and a multi-agent spec for the StockSense paper-trading agent.

**Status: drafts.** The `SKILL.md` layout (YAML `name` + `description`, then Markdown
instructions) is the common convention, but I have not checked it against Qoder's current
docs. Adjust the frontmatter to whatever Qoder expects; the instruction bodies only call
the repo's own Python, so they are format-independent.

All commands run from `stocksense-ai/backend`.

| Role | Skill | What it runs |
|---|---|---|
| Research | `market-research` | `scripts/ingest_news.py` |
| Signal | `signal-generation` | `app.ml.predictor.run_prediction` via the loop |
| Risk officer (veto) | `risk-officer` | `app/agent/risk.py` limits, `KILL_SWITCH` file |
| Execution | `paper-execution` | `python -m app.agent.loop --broker moomoo` |
| Reporting | `performance-report` | `python -m app.agent.report` |

See `agents/orchestrator.md` for handoffs, the veto rule and the schedule.

## Load into Qoder

1. Copy `qoder/skills/*` into your Qoder skills location and `agents/orchestrator.md` into
   a Cloud Agent definition (check Qoder's docs for the exact paths).
2. Give the agent a shell with this repo checked out and OpenD reachable
   (`MOOMOO_HOST`/`MOOMOO_PORT`).
3. Run one cycle with `--broker sim` before pointing it at the paper account.

## Safety

The Moomoo broker is hard-wired to the simulated environment. The kill switch
(`touch KILL_SWITCH` in the working directory) flattens the book on the next cycle.
