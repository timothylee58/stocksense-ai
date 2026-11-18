"""Pre-trade risk gate.

Every order intent is evaluated before it reaches the paper broker.  The gate
is a pure function over (intent, portfolio, limits, kill-switch) so the same
logic can be unit-tested and replayed from the decision ledger.

Kill switch semantics: when active, new BUY orders are blocked and SELL orders
remain allowed so the book can be flattened.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.redis_client import cache_get, get_redis
from app.schemas.risk import (
    KillSwitchState,
    OrderIntent,
    OrderSide,
    PortfolioSnapshot,
    RiskCheck,
    RiskDecision,
    RiskLimits,
)

logger = logging.getLogger(__name__)

KILL_SWITCH_KEY = "risk:kill_switch"

KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
ORDER_NOTIONAL_EXCEEDED = "ORDER_NOTIONAL_EXCEEDED"
POSITION_LIMIT_EXCEEDED = "POSITION_LIMIT_EXCEEDED"
GROSS_EXPOSURE_EXCEEDED = "GROSS_EXPOSURE_EXCEEDED"
INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
CASH_BUFFER_BREACHED = "CASH_BUFFER_BREACHED"
DAILY_LOSS_LIMIT_BREACHED = "DAILY_LOSS_LIMIT_BREACHED"
MAX_DRAWDOWN_BREACHED = "MAX_DRAWDOWN_BREACHED"
POSITION_NOT_HELD = "POSITION_NOT_HELD"

# In-process fallback when Redis is unavailable.
_memory_kill_switch = KillSwitchState()


def _check(name: str, passed: bool, code: str, detail: str) -> RiskCheck:
    return RiskCheck(name=name, passed=passed, code="" if passed else code, detail=detail)


def evaluate_order(
    decision_id: str,
    intent: OrderIntent,
    portfolio: PortfolioSnapshot,
    limits: RiskLimits,
    kill_switch: KillSwitchState | None = None,
) -> RiskDecision:
    """Evaluate one order. No I/O — deterministic and replayable."""
    ks = kill_switch or KillSwitchState()
    equity = portfolio.equity
    held = portfolio.position_for(intent.ticker)
    gross_before = sum(abs(p.market_value) for p in portfolio.positions)
    notional = round(intent.quantity * intent.price, 2)
    is_buy = intent.side == OrderSide.BUY
    checks: list[RiskCheck] = []

    checks.append(_check(
        "kill_switch",
        not (ks.enabled and is_buy),
        KILL_SWITCH_ACTIVE,
        "kill switch active — new buys blocked, sells allowed" if ks.enabled else "inactive",
    ))

    if is_buy:
        checks.append(_check(
            "order_notional",
            notional <= limits.max_order_notional,
            ORDER_NOTIONAL_EXCEEDED,
            f"{notional:.2f} vs limit {limits.max_order_notional:.2f}",
        ))

        projected_position_value = abs(held.market_value) + notional
        projected_position_pct = projected_position_value / equity
        checks.append(_check(
            "position_limit",
            projected_position_pct <= limits.max_position_pct,
            POSITION_LIMIT_EXCEEDED,
            f"{projected_position_pct:.1%} vs limit {limits.max_position_pct:.1%}",
        ))

        projected_gross = gross_before + notional
        projected_gross_pct = projected_gross / equity
        checks.append(_check(
            "gross_exposure",
            projected_gross_pct <= limits.max_gross_exposure_pct,
            GROSS_EXPOSURE_EXCEEDED,
            f"{projected_gross_pct:.1%} vs limit {limits.max_gross_exposure_pct:.1%}",
        ))

        cash_after = portfolio.cash - notional
        checks.append(_check(
            "cash_available",
            cash_after >= 0,
            INSUFFICIENT_CASH,
            f"cash {portfolio.cash:.2f}, required {notional:.2f}",
        ))
        if cash_after >= 0:
            buffer_after = cash_after / equity
            checks.append(_check(
                "cash_buffer",
                buffer_after >= limits.min_cash_buffer_pct,
                CASH_BUFFER_BREACHED,
                f"{buffer_after:.1%} vs floor {limits.min_cash_buffer_pct:.1%}",
            ))

        day_pnl_pct = portfolio.day_pnl / equity
        checks.append(_check(
            "daily_loss",
            day_pnl_pct > -limits.max_daily_loss_pct,
            DAILY_LOSS_LIMIT_BREACHED,
            f"{day_pnl_pct:.2%} vs limit -{limits.max_daily_loss_pct:.2%}",
        ))

        peak = portfolio.peak_equity or equity
        drawdown_pct = max(0.0, (peak - equity) / peak)
        checks.append(_check(
            "drawdown",
            drawdown_pct < limits.max_drawdown_pct,
            MAX_DRAWDOWN_BREACHED,
            f"{drawdown_pct:.1%} vs limit {limits.max_drawdown_pct:.1%}",
        ))
    else:
        projected_gross_pct = max(0.0, gross_before - notional) / equity
        projected_position_pct = max(0.0, abs(held.market_value) - notional) / equity
        cash_after = portfolio.cash + notional
        day_pnl_pct = portfolio.day_pnl / equity
        peak = portfolio.peak_equity or equity
        drawdown_pct = max(0.0, (peak - equity) / peak)
        checks.append(_check(
            "position_held",
            intent.quantity <= held.quantity,
            POSITION_NOT_HELD,
            f"sell {intent.quantity} vs held {held.quantity} — shorting disabled",
        ))

    failed = [c for c in checks if not c.passed]
    return RiskDecision(
        decision_id=decision_id,
        approved=not failed,
        reason_codes=sorted({c.code for c in failed}),
        checks=checks,
        order=intent,
        account_id=portfolio.account_id,
        kill_switch_active=ks.enabled,
        notional=notional,
        projected_position_pct=round(projected_position_pct, 6),
        projected_gross_pct=round(projected_gross_pct, 6),
        cash_after=round(cash_after, 2),
        day_pnl_pct=round(day_pnl_pct, 6),
        drawdown_pct=round(drawdown_pct, 6),
    )


async def get_kill_switch() -> KillSwitchState:
    cached = await cache_get(KILL_SWITCH_KEY)
    if cached:
        try:
            return KillSwitchState.model_validate(cached)
        except Exception:
            logger.warning("Ignoring malformed kill-switch payload")
    return _memory_kill_switch


async def set_kill_switch(enabled: bool, reason: str, actor: str) -> KillSwitchState:
    global _memory_kill_switch
    state = KillSwitchState(
        enabled=enabled,
        reason=reason.strip(),
        actor=actor.strip(),
        updated_at=datetime.now(timezone.utc),
    )
    _memory_kill_switch = state
    try:
        r = get_redis()
        await r.set(KILL_SWITCH_KEY, state.model_dump_json())
    except Exception as exc:
        logger.warning("Kill switch persisted in memory only: %s", exc)
    return state
