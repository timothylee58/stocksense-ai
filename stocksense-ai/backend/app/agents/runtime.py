"""Agent run loop — Phases 1 (shadow) and 2/3 (paper + audit).

One session drives the seven templates in order: Supervisor health → Data
Steward → Technical + News → ensemble → Risk Reviewer → Executor (paper only)
→ Auditor.  Every step is journaled with artifact hashes and the strategy
version, and every order decision goes through the same pre-trade gate as the
manual route.

Shadow phase evaluates and ledgers decisions with ``dry_run=True`` and never
calls an order tool.  Paper phase submits LIMIT orders through the Executor
binding, one per idempotency key (the decision id).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import date, datetime, timedelta
from datetime import timezone

from app.agents.artifacts import (
    AuditReport,
    Bar,
    Dataset,
    Direction,
    ExecutionRecord,
    Fill,
    NameStatus,
    Quote,
    RiskVerdict,
    RunRecord,
    Universe,
)
from app.agents.bindings import AgentBindings, LocalBindings, PolicyViolation
from app.agents.journal import Journal, artifact_sha256
from app.agents.signals import (
    ensemble,
    intent_hash,
    propose_quantity,
    sentiment_signal,
    technical_signal,
)
from app.core.config import get_settings
from app.schemas.risk import (
    OrderExecution,
    OrderIntent,
    OrderSide,
    OrderType,
    PortfolioSnapshot,
    RiskDecision,
    RiskLimits,
)
from app.services import decision_ledger
from app.services.risk_gate import evaluate_order, get_kill_switch

logger = logging.getLogger(__name__)

SHADOW = "shadow"
PAPER = "paper"

_CLAMPABLE = {
    "POSITION_LIMIT_EXCEEDED",
    "ORDER_NOTIONAL_EXCEEDED",
    "CASH_BUFFER_BREACHED",
    "INSUFFICIENT_CASH",
}

_memory_claims: set[str] = set()
_claim_lock = threading.Lock()


class RunHalt(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def latest_session_date(now: datetime | None = None) -> date:
    d = (now or datetime.now(timezone.utc)).date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


async def _claim_idempotency(key: str) -> bool:
    try:
        from app.core.redis_client import get_redis

        return bool(await get_redis().set(f"order:idem:{key}", "1", nx=True, ex=86_400))
    except Exception:
        with _claim_lock:
            if key in _memory_claims:
                return False
            _memory_claims.add(key)
            return True


def _direction(value) -> Direction:
    if isinstance(value, Direction):
        return value
    try:
        return Direction(str(value).upper())
    except ValueError:
        return Direction.NEUTRAL


class AgentRuntime:
    def __init__(
        self,
        phase: str = SHADOW,
        bindings: AgentBindings | None = None,
        journal: Journal | None = None,
        symbols: list[str] | None = None,
    ):
        if phase not in (SHADOW, PAPER):
            raise ValueError(f"unknown phase {phase!r}; expected {SHADOW!r} or {PAPER!r}")
        settings = get_settings()
        self.phase = phase
        self.bindings = bindings or LocalBindings()
        self.journal = journal or Journal()
        self.symbols = [s.strip().upper() for s in (symbols or settings.challenge_universe)]
        self.strategy_version = settings.challenge_strategy_version
        self.settings = settings

    # ── public entry point ───────────────────────────────────────────────────
    async def run_session(self, session_date: date | None = None, phase: str | None = None) -> dict:
        phase = phase or self.phase
        if phase not in (SHADOW, PAPER):
            raise ValueError(f"unknown phase {phase!r}")
        session_date = session_date or latest_session_date()

        existing = self._existing_run(session_date, phase)
        if existing is not None:
            return existing

        run_id = f"run-{session_date.isoformat()}-{phase}-{uuid.uuid4().hex[:8]}"
        pending = [NameStatus(symbol=s, status="pending") for s in self.symbols]
        started = RunRecord(
            run_id=run_id,
            session_date=session_date,
            strategy_version=self.strategy_version,
            status="running",
            per_name_status=pending,
        )
        self._append(run_id, "run_started", {
            "run_id": run_id,
            "session_date": session_date.isoformat(),
            "phase": phase,
            "strategy_version": self.strategy_version,
            "symbols": self.symbols,
            "status": "running",
        }, run_record=started)

        try:
            universe = Universe(session_date=session_date, symbols=self.symbols)
        except ValueError as exc:
            return self._halt(run_id, session_date, phase, f"invalid universe: {exc}", pending)

        try:
            health = await self.bindings.health("supervisor")
        except PolicyViolation:
            raise
        except Exception as exc:
            health = {"ok": False, "reason": f"health call failed: {exc}"}
        if not health.get("ok"):
            return self._halt(
                run_id, session_date, phase,
                f"health check failed: {health.get('reason', 'unknown')}", pending,
            )

        statuses: list[NameStatus] = []
        decision_ids: list[str] = []
        executions: list[dict] = []
        evaluations = 0

        for symbol in universe.symbols:
            try:
                result = await self._evaluate_symbol(run_id, session_date, phase, symbol)
            except RunHalt as exc:
                return self._halt(
                    run_id, session_date, phase, exc.reason,
                    [NameStatus(symbol=s, status="aborted") for s in universe.symbols],
                )
            except PolicyViolation:
                raise
            except Exception as exc:
                logger.warning("agent evaluation failed for %s: %s", symbol, exc)
                self._append(run_id, "name_denied", {
                    "symbol": symbol,
                    "reason": f"EVALUATION_FAILED: {exc}",
                })
                statuses.append(NameStatus(symbol=symbol, status="denied"))
                continue
            statuses.append(NameStatus(symbol=symbol, status=result["status"]))
            decision_ids.extend(result["decision_ids"])
            executions.extend(result["executions"])
            evaluations += 1

        return self._finish(run_id, session_date, phase, statuses, decision_ids, executions, evaluations)

    # ── per-symbol pipeline ──────────────────────────────────────────────────
    async def _evaluate_symbol(
        self, run_id: str, session_date: date, phase: str, symbol: str
    ) -> dict:
        # Data Steward
        raw = await self.bindings.dataset("data_steward", symbol)
        now = datetime.now(timezone.utc)
        if raw.get("valid") is False:
            reason = raw.get("deny_reason") or "MISSING_QUOTE"
            self._append(run_id, "name_denied", {"symbol": symbol, "deny_reason": reason})
            return {"status": "denied", "decision_ids": [], "executions": []}

        q = raw.get("quote") or {}
        quote_ts = q.get("ts")
        if quote_ts is None:
            self._append(run_id, "name_denied", {"symbol": symbol, "deny_reason": "MISSING_QUOTE"})
            return {"status": "denied", "decision_ids": [], "executions": []}
        age_s = max(0.0, (now - quote_ts).total_seconds())
        from app.agents.artifacts import MAX_QUOTE_AGE_S

        dataset = Dataset(
            symbol=symbol,
            quote=Quote(
                symbol=symbol,
                price=float(q["price"]),
                prev_close=q.get("prev_close"),
                ts=quote_ts,
                source=q.get("source", "moomoo"),
                delayed=bool(q.get("delayed", False)),
            ),
            bars=list(raw.get("bars") or []),
            age_s=age_s,
            source=str(raw.get("source") or q.get("source") or "moomoo"),
            valid=age_s <= MAX_QUOTE_AGE_S,
            deny_reason=None if age_s <= MAX_QUOTE_AGE_S else "STALE_QUOTE",
        )
        dataset_hash = artifact_sha256(dataset)
        self._append(run_id, "dataset", dataset.model_dump(mode="json"), dataset=dataset)
        if not dataset.valid:
            return {"status": "denied", "decision_ids": [], "executions": []}

        # Technical Analyst + LSTM input
        ml = await self.bindings.ml("technical", symbol, dataset.bars)
        xgb_signal, xgb_conf = ml.get("xgboost", ("HOLD", 0.0))
        lstm_dir_raw, lstm_conf = ml.get("lstm", ("NEUTRAL", 0.0))
        atr = ml.get("atr")
        technical = technical_signal(
            symbol,
            xgb_signal,
            float(xgb_conf),
            dataset.bars,
            dataset_ref=f"dataset:{symbol}:{session_date.isoformat()}",
            dataset_sha256=dataset_hash,
        )
        self._append(run_id, "technical", technical.model_dump(mode="json"), technical=technical)
        if technical.status == "insufficient_data":
            return {"status": "no_trade", "decision_ids": [], "executions": []}

        # News Analyst
        score, headlines = await self.bindings.news("news", symbol)
        sentiment = sentiment_signal(symbol, score, headlines)
        self._append(run_id, "sentiment", sentiment.model_dump(mode="json"), sentiment=sentiment)

        # Ensemble
        direction, confidence, parts = ensemble(
            xgb_signal,
            float(xgb_conf),
            sentiment,
            _direction(lstm_dir_raw),
            float(lstm_conf),
            float(self.settings.challenge_signal_threshold),
        )
        self._append(run_id, "evaluation", {
            "symbol": symbol,
            "direction": direction.value,
            "confidence": confidence,
            "components": parts,
        })
        if direction == Direction.NEUTRAL:
            return {"status": "no_trade", "decision_ids": [], "executions": []}

        # Risk Reviewer — sizing + gate
        try:
            portfolio = await self.bindings.portfolio("risk_reviewer")
        except PolicyViolation:
            raise
        except Exception as exc:
            logger.warning("portfolio unavailable for %s: %s", symbol, exc)
            self._append(run_id, "name_denied", {"symbol": symbol, "deny_reason": "ACCOUNT_UNAVAILABLE"})
            return {"status": "denied", "decision_ids": [], "executions": []}

        held = portfolio.position_for(symbol)
        limits = RiskLimits.from_settings()
        if direction == Direction.UP:
            side = OrderSide.BUY
            quantity = propose_quantity(
                equity=portfolio.equity,
                cash=portfolio.cash,
                price=dataset.quote.price,
                atr=atr,
                held_qty=held.quantity,
                held_value=abs(held.market_value),
                risk_per_trade_pct=float(self.settings.risk_per_trade_pct),
                max_position_pct=limits.max_position_pct,
                max_order_notional=limits.max_order_notional,
                min_cash_buffer_pct=limits.min_cash_buffer_pct,
            )
            if quantity < 1:
                self._append(run_id, "no_trade", {
                    "symbol": symbol, "reason": "SIZE_BELOW_ONE_SHARE",
                })
                return {"status": "no_trade", "decision_ids": [], "executions": []}
        else:
            side = OrderSide.SELL
            quantity = int(held.quantity)
            if quantity < 1:
                self._append(run_id, "no_trade", {
                    "symbol": symbol, "reason": "NO_POSITION_TO_SELL",
                })
                return {"status": "no_trade", "decision_ids": [], "executions": []}

        decision_id = str(uuid.uuid4())
        intent = OrderIntent(
            ticker=symbol,
            side=side,
            quantity=float(quantity),
            price=dataset.quote.price,
            order_type=OrderType.LIMIT,
            quote_ts=dataset.quote.ts,
            dry_run=phase == SHADOW,
            strategy_id="stocksense-challenge",
            rationale=f"ensemble {direction.value} conf={confidence:.2f}",
            idempotency_key=decision_id,
            model_version=self.strategy_version,
        )
        kill = await get_kill_switch()
        decision = evaluate_order(decision_id, intent, portfolio, limits, kill)

        clamped = None
        if not decision.approved and side == OrderSide.BUY and set(decision.reason_codes) <= _CLAMPABLE:
            clamped = self._clamped_quantity(intent, portfolio, limits)
            if clamped and clamped < quantity:
                intent = intent.model_copy(update={"quantity": float(clamped)})
                decision = evaluate_order(decision_id, intent, portfolio, limits, kill)
            else:
                clamped = None

        verdict = RiskVerdict(
            approved=decision.approved,
            clamped_qty=clamped,
            reasons=[] if decision.approved else list(decision.reason_codes),
            limits_hit=[c.name for c in decision.checks if not c.passed],
            intent_hash=intent_hash(intent),
        )
        store = await asyncio.to_thread(decision_ledger.record_decision, decision, "agent-runtime")
        if store == "unavailable":
            raise RunHalt("decision ledger unavailable (fail-closed)")
        self._append(run_id, "risk_verdict", {
            "decision_id": decision_id,
            "storage": store,
            "dry_run": intent.dry_run,
            "intent": intent.model_dump(mode="json"),
            "decision": decision.model_dump(mode="json"),
            "verdict": verdict.model_dump(mode="json"),
        }, verdict=verdict, order_intent=intent)

        if not verdict.approved:
            return {"status": "rejected", "decision_ids": [decision_id], "executions": []}

        if phase == SHADOW:
            self._append(run_id, "execution_skipped", {
                "decision_id": decision_id,
                "reason": "shadow phase — no order tool called",
            })
            return {"status": "approved", "decision_ids": [decision_id], "executions": []}

        execution = await self._execute(run_id, decision_id, intent, verdict, decision)
        return {
            "status": "filled" if execution["status"] == "filled" else "submitted",
            "decision_ids": [decision_id],
            "executions": [execution],
        }

    def _clamped_quantity(
        self, intent: OrderIntent, portfolio: PortfolioSnapshot, limits: RiskLimits
    ) -> int | None:
        held = portfolio.position_for(intent.ticker)
        price = intent.price
        q = min(
            limits.max_order_notional / price,
            max(0.0, limits.max_position_pct * portfolio.equity - abs(held.market_value)) / price,
            max(0.0, portfolio.cash - limits.min_cash_buffer_pct * portfolio.equity) / price,
        )
        qty = int(q)
        return qty if qty >= 1 else None

    async def _execute(
        self,
        run_id: str,
        decision_id: str,
        intent: OrderIntent,
        verdict: RiskVerdict,
        decision: RiskDecision,
    ) -> dict:
        # Verdict must be approved and bound to exactly this intent.
        if not verdict.approved or verdict.intent_hash != intent_hash(intent):
            record = ExecutionRecord(intent_id=decision_id, status="risk_reject")
            self._append(run_id, "execution", record.model_dump(mode="json"), execution=record)
            return record.model_dump(mode="json")

        if not await _claim_idempotency(intent.idempotency_key):
            execution = OrderExecution(
                status="duplicate_blocked",
                message=f"idempotency key {intent.idempotency_key} already used",
                dry_run=False,
            )
            await asyncio.to_thread(decision_ledger.record_execution, decision, execution, "agent-runtime")
            record = ExecutionRecord(intent_id=decision_id, status="duplicate")
            self._append(run_id, "execution", record.model_dump(mode="json"), execution=record)
            return record.model_dump(mode="json")

        try:
            execution = await self.bindings.place_order("executor", intent, decision_id)
        except PolicyViolation:
            raise
        except Exception as exc:
            logger.error("paper execution failed for %s: %s", intent.ticker, exc)
            execution = OrderExecution(status="failed", message=str(exc), dry_run=False)

        storage = await asyncio.to_thread(
            decision_ledger.record_execution, decision, execution, "agent-runtime"
        )
        if storage == "unavailable":
            raise RunHalt("decision ledger unavailable after execution (fail-closed)")

        status = {
            "filled": "filled",
            "submitted": "submitted",
            "duplicate_blocked": "duplicate",
            "failed": "failed",
            "timeout": "timeout",
        }.get(execution.status, "failed")
        fills = []
        if status == "filled":
            fills = [Fill(qty=intent.quantity, price=intent.price, ts=execution.executed_at)]
        record = ExecutionRecord(
            intent_id=decision_id,
            order_id=execution.order_id,
            status=status,
            fills=fills,
        )
        self._append(run_id, "execution", {
            **record.model_dump(mode="json"),
            "broker_message": execution.message,
        }, execution=record)
        return record.model_dump(mode="json")

    # ── run end ──────────────────────────────────────────────────────────────
    def _finish(
        self,
        run_id: str,
        session_date: date,
        phase: str,
        statuses: list[NameStatus],
        decision_ids: list[str],
        executions: list[dict],
        evaluations: int,
    ) -> dict:
        chain_ok, chain_breaks = self.journal.verify(run_id=run_id)
        breaks = list(chain_breaks)
        if phase == SHADOW and executions:
            breaks.append("shadow phase produced executions")
        if phase == PAPER:
            for execution in executions:
                if execution.get("status") == "failed":
                    breaks.append(f"failed execution {execution.get('intent_id')}")

        audit = AuditReport(
            run_id=run_id,
            decisions=len(decision_ids),
            executions=len(executions),
            breaks=breaks,
            hash_chain_ok=chain_ok,
        )
        self._append(run_id, "audit", audit.model_dump(mode="json"), audit_report=audit)

        final = RunRecord(
            run_id=run_id,
            session_date=session_date,
            strategy_version=self.strategy_version,
            status="completed" if not breaks else "halted",
            per_name_status=statuses,
            halt_reason=None if not breaks else "; ".join(breaks),
        )
        self._append(run_id, "run_finished", {
            "status": final.status,
            "phase": phase,
            "run_record": final.model_dump(mode="json"),
            "evaluations": evaluations,
        }, run_record=final)
        return {
            "run": final.model_dump(mode="json"),
            "audit": audit.model_dump(mode="json"),
            "decisions": len(decision_ids),
            "executions": executions,
            "reused": False,
        }

    def _halt(
        self,
        run_id: str,
        session_date: date,
        phase: str,
        reason: str,
        pending: list[NameStatus],
    ) -> dict:
        record = RunRecord(
            run_id=run_id,
            session_date=session_date,
            strategy_version=self.strategy_version,
            status="aborted",
            per_name_status=pending,
            halt_reason=reason,
        )
        audit = AuditReport(
            run_id=run_id, decisions=0, executions=0, breaks=[reason], hash_chain_ok=True
        )
        self._append(run_id, "audit", audit.model_dump(mode="json"), audit_report=audit)
        self._append(run_id, "run_finished", {
            "status": "aborted",
            "phase": phase,
            "run_record": record.model_dump(mode="json"),
            "evaluations": 0,
        }, run_record=record)
        return {
            "run": record.model_dump(mode="json"),
            "audit": audit.model_dump(mode="json"),
            "decisions": 0,
            "executions": [],
            "reused": False,
        }

    def _existing_run(self, session_date: date, phase: str) -> dict | None:
        started = self.journal.find_run(session_date.isoformat(), self.strategy_version, phase)
        if started is None:
            return None
        run_id = started["run_id"]
        events = self.journal.read(run_id=run_id)
        final = None
        audit = None
        for event in events:
            if event.get("event_type") == "run_finished":
                final = event.get("payload", {}).get("run_record")
            elif event.get("event_type") == "audit":
                audit = event.get("payload")
        if final is None:
            final = {
                "run_id": run_id,
                "session_date": session_date.isoformat(),
                "strategy_version": self.strategy_version,
                "status": "running",
                "per_name_status": [],
                "halt_reason": None,
            }
        return {
            "run": final,
            "audit": audit,
            "decisions": (audit or {}).get("decisions", 0),
            "executions": [],
            "reused": True,
        }

    def _append(self, run_id: str, event_type: str, payload: dict, **artifacts) -> None:
        hashes = {
            name: artifact_sha256(artifact)
            for name, artifact in artifacts.items()
        }
        self.journal.append(
            run_id=run_id,
            strategy_version=self.strategy_version,
            event_type=event_type,
            payload=payload,
            artifact_hashes=hashes,
        )


__all__ = ["AgentRuntime", "SHADOW", "PAPER", "latest_session_date"]
