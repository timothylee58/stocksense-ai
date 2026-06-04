"""AI-generated stock briefing via Claude API (structured input → structured output)."""
from __future__ import annotations

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None

SECTOR_PEERS: dict[str, list[str]] = {
    "Technology":    ["AAPL", "NVDA", "MSFT", "AMD", "GOOGL"],
    "Communication": ["GOOGL", "META", "NFLX"],
    "Consumer":      ["AMZN", "WMT"],
    "Automotive":    ["TSLA"],
    "Financials":    ["BRK-B", "JPM", "V"],
    "Healthcare":    ["LLY"],
    "Energy":        ["XOM"],
    "Retail":        ["WMT", "AMZN"],
    "Media":         ["NFLX", "META"],
}

_BRIEFING_SCHEMA = {
    "name": "stock_briefing",
    "description": "Structured four-section stock briefing",
    "input_schema": {
        "type": "object",
        "properties": {
            "sector_context": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                },
                "required": ["headline", "bullets"],
            },
            "risk_flags": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                },
                "required": ["headline", "bullets"],
            },
            "peer_comparison": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                },
                "required": ["headline", "bullets"],
            },
            "analyst_framing": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                },
                "required": ["headline", "bullets"],
            },
            "overall_summary": {"type": "string"},
        },
        "required": ["sector_context", "risk_flags", "peer_comparison", "analyst_framing", "overall_summary"],
    },
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        from app.core.config import get_settings
        settings = get_settings()
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    return _client


def generate_briefing(ticker: str, prediction: dict) -> dict:
    """
    Call Claude to produce a four-section briefing for the given ticker.

    Sections: sector_context, risk_flags, peer_comparison, analyst_framing.
    Uses tool_use (structured output) for guaranteed JSON shape.
    """
    name = prediction.get("name", ticker)
    sector = prediction.get("sector", "Unknown")
    signal = prediction.get("signal", "HOLD")
    confidence = prediction.get("confidence", 0.5)
    trend = prediction.get("trend", "SIDEWAYS")
    current_price = prediction.get("current_price", 0.0)
    price_change_pct = prediction.get("price_change_pct", 0.0)
    rsi = prediction.get("rsi")
    macd = prediction.get("macd")
    sentiment = prediction.get("sentiment_score", 0.5)
    timing = prediction.get("timing") or {}
    action = timing.get("action", "HOLD")
    risk_level = timing.get("risk_level", "MEDIUM")
    timing_score = timing.get("timing_score", 5.0)
    rationale = timing.get("rationale") or []

    peers = [p for p in SECTOR_PEERS.get(sector, []) if p != ticker][:3]
    peers_str = ", ".join(peers) if peers else "sector peers"

    rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
    macd_str = f"{macd:.3f}" if macd is not None else "N/A"
    rationale_str = "; ".join(rationale[:3]) if rationale else "None"

    prompt = f"""You are a senior equity analyst producing a concise structured briefing.

## Input Data
- Stock: {name} ({ticker}) | Sector: {sector}
- Price: ${current_price:.2f} ({price_change_pct:+.2f}% 7d)
- ML Signal: {signal} @ {confidence:.0%} confidence | Trend: {trend}
- Timing: score {timing_score:.1f}/10 | action {action} | risk {risk_level}
- RSI: {rsi_str} | MACD: {macd_str} | Sentiment: {sentiment:.2f}
- Key signals: {rationale_str}
- Sector peers: {peers_str}

## Task
Produce a four-section briefing. Keep each headline under 15 words; bullets under 20 words each.

**sector_context** — macro/sector tailwinds & headwinds, regulatory or cycle context.
**risk_flags** — 3 specific risk factors (valuation, technical, macro, or company-specific).
**peer_comparison** — how {ticker} stands relative to {peers_str} on signal strength, momentum, and valuation posture.
**analyst_framing** — how sell-side analysts typically frame this setup; what the combined signals imply.
**overall_summary** — one punchy sentence capturing the investment thesis.

Be precise. No generic platitudes. Ground everything in the data above."""

    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        tools=[_BRIEFING_SCHEMA],
        tool_choice={"type": "tool", "name": "stock_briefing"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in message.content:
        if block.type == "tool_use" and block.name == "stock_briefing":
            return block.input

    raise RuntimeError("Claude did not return a structured briefing tool call")
