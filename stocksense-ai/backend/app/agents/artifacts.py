"""Artifact contracts passed between the seven agents.

These are the only shapes an agent may emit.  Signals carry ``confidence`` in
[0, 1] and provenance refs; nothing here can carry raw model logits, model
weights, or raw feature vectors.  The backend validates agent output against
these models before it reaches the decision ledger.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_QUOTE_AGE_S = 60.0

DenyReason = Literal[
    "STALE_QUOTE",
    "MISSING_QUOTE",
    "ENTITLEMENT_DENIED",
    "OUTSIDE_UNIVERSE",
    "INSUFFICIENT_BARS",
]


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


class ProvenanceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "dataset", "technical", "sentiment", "decision", "verdict", "execution", "ledger"
    ]
    ref: str = Field(min_length=1)
    sha256: str = ""


class Universe(BaseModel):
    """Supervisor input: the fixed US paper universe for one session."""

    model_config = ConfigDict(extra="forbid")

    session_date: date
    symbols: list[str] = Field(min_length=1, max_length=10)

    @field_validator("symbols")
    @classmethod
    def _us_only_unique(cls, v: list[str]) -> list[str]:
        from app.services.risk_gate import is_us_ticker

        cleaned = [s.strip().upper() for s in v]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("duplicate symbols in universe")
        outside = [s for s in cleaned if not is_us_ticker(s)]
        if outside:
            raise ValueError(f"universe must be US-only; outside: {outside}")
        return cleaned


class NameStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    status: Literal[
        "pending", "denied", "no_trade", "approved", "rejected", "submitted", "filled", "aborted"
    ]


class RunRecord(BaseModel):
    """Supervisor output.  Idempotency key is (session_date, strategy_version)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    session_date: date
    strategy_version: str = Field(min_length=1)
    status: Literal["running", "completed", "halted", "aborted"]
    per_name_status: list[NameStatus] = Field(default_factory=list)
    halt_reason: str | None = None

    @model_validator(mode="after")
    def _halt_consistency(self) -> "RunRecord":
        if self.status in ("halted", "aborted") and not self.halt_reason:
            raise ValueError("halted/aborted run must state halt_reason")
        return self


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    price: float = Field(gt=0)
    prev_close: float | None = Field(default=None, gt=0)
    ts: datetime
    source: Literal["moomoo", "yfinance", "demo"]
    delayed: bool = False


class Bar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)


class Dataset(BaseModel):
    """Data Steward output.  valid=False always carries a deny_reason."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    quote: Quote
    bars: list[Bar] = Field(default_factory=list)
    age_s: float = Field(ge=0)
    source: str = Field(min_length=1)
    valid: bool
    deny_reason: DenyReason | None = None

    @model_validator(mode="after")
    def _freshness_consistency(self) -> "Dataset":
        if self.valid:
            if self.deny_reason is not None:
                raise ValueError("valid dataset cannot carry deny_reason")
            if self.age_s > MAX_QUOTE_AGE_S:
                raise ValueError(f"quote age {self.age_s}s exceeds {MAX_QUOTE_AGE_S}s")
        elif self.deny_reason is None:
            raise ValueError("invalid dataset must state deny_reason")
        return self


class TechnicalSignal(BaseModel):
    """Technical Analyst output.  insufficient_data ⇒ NEUTRAL with confidence 0."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    features: dict[str, float] = Field(default_factory=dict)
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["ok", "insufficient_data"] = "ok"
    provenance: list[ProvenanceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def _insufficient_consistency(self) -> "TechnicalSignal":
        if self.status == "insufficient_data":
            if self.direction != Direction.NEUTRAL or self.confidence != 0.0:
                raise ValueError("insufficient_data requires direction=NEUTRAL and confidence=0")
        return self


class SentimentSignal(BaseModel):
    """News Analyst output.  Zero headlines ⇒ neutral with confidence 0."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    score: float = Field(ge=-1.0, le=1.0)
    n_headlines: int = Field(ge=0)
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[ProvenanceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def _empty_news_consistency(self) -> "SentimentSignal":
        if self.n_headlines == 0 and (
            self.score != 0.0 or self.direction != Direction.NEUTRAL or self.confidence != 0.0
        ):
            raise ValueError("zero headlines require score=0, NEUTRAL, confidence=0")
        return self


class RiskVerdict(BaseModel):
    """Risk Reviewer output.  Bound to the exact intent via intent_hash."""

    model_config = ConfigDict(extra="forbid")

    approved: bool
    clamped_qty: float | None = Field(default=None, gt=0)
    reasons: list[str] = Field(default_factory=list)
    limits_hit: list[str] = Field(default_factory=list)
    intent_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def _verdict_consistency(self) -> "RiskVerdict":
        if self.approved and self.reasons:
            raise ValueError("approved verdict cannot carry rejection reasons")
        if not self.approved and not self.reasons:
            raise ValueError("veto must state at least one reason code")
        return self


class Fill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    ts: datetime


class ExecutionRecord(BaseModel):
    """Executor output.  DUPLICATE/RISK_REJECT never retry with a new key."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str = Field(min_length=1)
    order_id: str = ""
    status: Literal["submitted", "filled", "duplicate", "risk_reject", "failed", "timeout"]
    fills: list[Fill] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_consistency(self) -> "ExecutionRecord":
        if self.status == "filled" and not self.fills:
            raise ValueError("filled execution must include at least one fill")
        return self


class AuditReport(BaseModel):
    """Auditor output.  breaks are blocking; hash_chain_ok must be explicit."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    decisions: int = Field(ge=0)
    executions: int = Field(ge=0)
    breaks: list[str] = Field(default_factory=list)
    hash_chain_ok: bool


__all__ = [
    "AuditReport",
    "Bar",
    "Dataset",
    "DenyReason",
    "Direction",
    "ExecutionRecord",
    "Fill",
    "MAX_QUOTE_AGE_S",
    "NameStatus",
    "ProvenanceRef",
    "Quote",
    "RiskVerdict",
    "RunRecord",
    "SentimentSignal",
    "TechnicalSignal",
    "Universe",
]
