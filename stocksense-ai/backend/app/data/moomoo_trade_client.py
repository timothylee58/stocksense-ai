"""Moomoo paper-trading adapter.

Hard safety rules:
- Only ``TrdEnv.SIMULATE`` is ever passed to the SDK.
- The configured paper account id must be present and must match the account
  returned by ``accinfo_query``.
- Any other trade environment raises ``LiveTradingForbidden`` before an SDK
  trade context is opened.

The SDK is imported lazily so the API still boots without OpenD installed.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import get_settings
from app.schemas.risk import OrderExecution, OrderIntent, OrderSide, OrderType, PortfolioPosition, PortfolioSnapshot

logger = logging.getLogger(__name__)


class PaperTradeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TradingDisabled(PaperTradeError):
    pass


class LiveTradingForbidden(PaperTradeError):
    pass


class PaperAccountIdRequired(PaperTradeError):
    pass


class PaperAccountMismatch(PaperTradeError):
    pass


class BrokerUnavailable(PaperTradeError):
    pass


_ctx = None
_ctx_lock = threading.Lock()


def reset_client() -> None:
    global _ctx
    with _ctx_lock:
        _ctx = None


def _sdk():
    try:
        import moomoo
        return moomoo
    except Exception as exc:
        raise BrokerUnavailable("MOOMOO_SDK_MISSING", f"moomoo SDK unavailable: {exc}") from exc


def _market_enum():
    sdk = _sdk()
    return getattr(sdk.TrdMarket, get_settings().moomoo_trd_market.upper(), sdk.TrdMarket.US)


def _firm_enum():
    sdk = _sdk()
    return getattr(sdk.SecurityFirm, get_settings().moomoo_security_firm.upper(), sdk.SecurityFirm.FUTUSECURITIES)


def _get_ctx():
    global _ctx
    if _ctx is not None:
        return _ctx
    with _ctx_lock:
        if _ctx is not None:
            return _ctx
        sdk = _sdk()
        s = get_settings()
        try:
            _ctx = sdk.OpenSecTradeContext(
                filter_trdmarket=_market_enum(),
                host=s.moomoo_host,
                port=s.moomoo_port,
                security_firm=_firm_enum(),
            )
        except Exception as exc:
            raise BrokerUnavailable("BROKER_UNAVAILABLE", f"Cannot open trade context: {exc}") from exc
        return _ctx


def _acc_id():
    raw = get_settings().moomoo_paper_account_id.strip()
    if not raw:
        raise PaperAccountIdRequired("PAPER_ACCOUNT_ID_REQUIRED", "MOOMOO_PAPER_ACCOUNT_ID is not set")
    return int(raw) if raw.isdigit() else raw


def _call(method, *args, **kwargs) -> Any:
    sdk = _sdk()
    ret, data = method(*args, **kwargs)
    if ret != sdk.RET_OK:
        raise BrokerUnavailable("BROKER_CALL_FAILED", f"{getattr(method, '__name__', 'call')}: {data}")
    return data


def _first(row: Any, names: tuple[str, ...], default: Any = None) -> Any:
    for name in names:
        try:
            value = row[name]
        except Exception:
            continue
        if value is not None:
            return value
    return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalise_ticker(code: str) -> str:
    text = str(code).strip().upper()
    if text.startswith("US."):
        return text[3:]
    if text.startswith("MY."):
        return f"{text[3:]}.KL"
    if text.startswith("HK."):
        return f"{text[3:]}.HK"
    if text.startswith("SG."):
        return f"{text[3:]}.SG"
    return text


def _to_moomoo_code(ticker: str) -> str:
    text = ticker.strip().upper()
    if text.startswith(("US.", "MY.", "HK.", "SG.")):
        return text
    if text.endswith(".KL"):
        return f"MY.{text[:-3]}"
    if text.endswith(".HK"):
        return f"HK.{text[:-3]}"
    if text.endswith(".SG"):
        return f"SG.{text[:-3]}"
    return f"US.{text}"


def verify_paper_guard() -> dict:
    """Validate config and the live account session. Never returns live info."""
    s = get_settings()
    if not s.moomoo_trade_enabled:
        raise TradingDisabled("TRADING_DISABLED", "MOOMOO_TRADE_ENABLED is false")
    if s.moomoo_trd_env.strip().upper() != "SIMULATE":
        raise LiveTradingForbidden(
            "LIVE_TRADING_FORBIDDEN",
            f"MOOMOO_TRD_ENV={s.moomoo_trd_env!r}; only SIMULATE is allowed",
        )

    acc_id = _acc_id()
    sdk = _sdk()
    data = _call(
        _get_ctx().accinfo_query,
        trd_env=sdk.TrdEnv.SIMULATE,
        acc_id=acc_id,
        refresh_cache=True,
    )
    if data is None or len(data) == 0:
        raise BrokerUnavailable("PAPER_ACCOUNT_NOT_FOUND", f"No simulated account for acc_id={acc_id}")
    row = data.iloc[0] if hasattr(data, "iloc") else data[0]

    reported_env = str(_first(row, ("trd_env", "trade_env"), "SIMULATE")).upper()
    if "SIMULATE" not in reported_env:
        raise LiveTradingForbidden(
            "LIVE_ACCOUNT_DETECTED",
            f"Broker returned trd_env={reported_env!r}; refusing to trade",
        )

    reported_id = str(_first(row, ("acc_id", "account_id"), "")).strip()
    if reported_id and reported_id != str(acc_id):
        raise PaperAccountMismatch(
            "PAPER_ACCOUNT_MISMATCH",
            f"Configured acc_id={acc_id} but broker returned {reported_id}",
        )

    return {
        "verified": True,
        "source": "moomoo",
        "trd_env": "SIMULATE",
        "account_id": str(acc_id),
        "currency": str(_first(row, ("currency", "base_currency"), "USD")),
        "equity": _as_float(_first(row, ("total_assets", "net_cash_power", "power"), 0.0)),
        "cash": _as_float(_first(row, ("cash", "available_cash"), 0.0)),
        "market_value": _as_float(_first(row, ("market_val", "securities_assets"), 0.0)),
    }


def get_paper_portfolio() -> PortfolioSnapshot:
    s = get_settings()
    sdk = _sdk()
    acc_id = _acc_id()
    account = verify_paper_guard()

    data = _call(
        _get_ctx().position_list_query,
        trd_env=sdk.TrdEnv.SIMULATE,
        acc_id=acc_id,
        refresh_cache=True,
    )
    positions: list[PortfolioPosition] = []
    if data is not None and len(data) > 0:
        rows = data.to_dict("records") if hasattr(data, "to_dict") else list(data)
        for row in rows:
            code = _first(row, ("code", "stock_code"), "")
            qty = _as_float(_first(row, ("qty", "quantity"), 0.0))
            if not code or abs(qty) < 1e-9:
                continue
            positions.append(PortfolioPosition(
                ticker=_normalise_ticker(code),
                quantity=qty,
                market_value=abs(_as_float(_first(row, ("market_val", "market_value"), 0.0))),
            ))

    equity = account["equity"] or (account["cash"] + account["market_value"])
    if equity <= 0:
        raise BrokerUnavailable("PAPER_EQUITY_UNAVAILABLE", "Broker returned non-positive equity")
    return PortfolioSnapshot(
        account_id=account["account_id"],
        equity=equity,
        cash=account["cash"],
        day_pnl=0.0,
        peak_equity=equity,
        positions=positions,
    )


def place_paper_order(intent: OrderIntent) -> OrderExecution:
    s = get_settings()
    sdk = _sdk()
    acc_id = _acc_id()
    verify_paper_guard()

    side = sdk.TrdSide.BUY if intent.side == OrderSide.BUY else sdk.TrdSide.SELL
    order_type = sdk.OrderType.MARKET if intent.order_type == OrderType.MARKET else sdk.OrderType.NORMAL
    data = _call(
        _get_ctx().place_order,
        price=float(intent.price),
        qty=float(intent.quantity),
        code=_to_moomoo_code(intent.ticker),
        trd_side=side,
        order_type=order_type,
        trd_env=sdk.TrdEnv.SIMULATE,
        acc_id=acc_id,
        remark=f"stocksense:{intent.strategy_id}"[:64],
    )
    row = data.iloc[0] if hasattr(data, "iloc") else data[0]
    order_id = str(_first(row, ("order_id", "orderid"), ""))
    logger.info("Paper order submitted %s %s qty=%s id=%s", intent.side.value, intent.ticker, intent.quantity, order_id)
    return OrderExecution(
        status="submitted",
        order_id=order_id,
        message=f"paper order accepted by {s.moomoo_trd_env}",
        dry_run=False,
    )
