# Moomoo API Integration Guide

This guide explains how to set up and use the moomoo API for real-time stock quotes and tick data in StockSense AI.

## Overview

The moomoo API integration provides:

- **Real-time quotes** (LV1/LV2) for US and Malaysia stocks
- **Tick-by-tick trade data** (up to 500 recent trades)
- **Order book depth** (Level 2 market data)
- **Pre/After hours data** for US stocks

## Prerequisites

### 1. Install moomoo-api

```bash
cd backend
pip install moomoo-api
```

### 2. Download and Configure moomoo OpenD

1. Download moomoo OpenD from the official moomoo website
2. Install and launch the OpenD gateway client
3. Log in with your moomoo account credentials
4. Note the host (default: `127.0.0.1`) and port (default: `11111`)

### 3. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` if needed:

```env
MOOMOO_HOST=127.0.0.1
MOOMOO_PORT=11111
MOOMOO_ENABLED=true
```

## Supported Markets

| Market | Code Format | Examples | Real-time Data |
|--------|-------------|----------|----------------|
| US | `US.{SYMBOL}` | `US.AAPL`, `US.NVDA` | LV1/LV2 |
| Malaysia | `MY.{SYMBOL}` | `MY.MAYBANK`, `MY.TENAGA` | Limited |
| Hong Kong | `HK.{SYMBOL}` | `HK.00700` | LV1/LV2 |
| Singapore | `SG.{SYMBOL}` | `SG.D05` | Limited |

## API Endpoints

### Get Real-Time Quote

```bash
GET /api/stocks/{ticker}/realtime
```

**Examples:**

```bash
# NVIDIA (US stock)
curl http://localhost:8000/api/stocks/US.NVDA/realtime

# Maybank (Malaysia stock)
curl http://localhost:8000/api/stocks/MY.MAYBANK/realtime

# Apple (shorthand - auto-prefixes US.)
curl http://localhost:8000/api/stocks/AAPL/realtime
```

**Response:**

```json
{
  "ticker": "NVDA",
  "market": "US",
  "last_price": 875.32,
  "open_price": 870.00,
  "high_price": 880.50,
  "low_price": 868.25,
  "prev_close_price": 872.00,
  "volume": 42500000,
  "turnover": 37187500000,
  "turnover_rate": 2.45,
  "bid_price": 875.25,
  "ask_price": 875.40,
  "bid_qty": 500,
  "ask_qty": 300,
  "price_spread": 0.15,
  "update_time": "2026-04-13T10:30:45.123456",
  "source": "moomoo"
}
```

### Get Tick Data

```bash
GET /api/stocks/{ticker}/ticks?num_ticks=100
```

**Example:**

```bash
curl http://localhost:8000/api/stocks/US.AAPL/ticks?num_ticks=50
```

**Response:**

```json
{
  "ticker": "US.AAPL",
  "ticks": [
    {
      "time": "2026-04-13T10:30:45",
      "price": 175.25,
      "volume": 1500,
      "turnover": 262875,
      "ticker_direction": "BUY",
      "type": "AUTO_MATCH"
    }
  ],
  "count": 50
}
```

### Get Order Book (Level 2)

```bash
GET /api/stocks/{ticker}/orderbook
```

**Example:**

```bash
curl http://localhost:8000/api/stocks/US.NVDA/orderbook
```

**Response:**

```json
{
  "ticker": "NVDA",
  "market": "US",
  "bids": [
    {"price": 875.25, "qty": 500},
    {"price": 875.00, "qty": 1200},
    {"price": 874.75, "qty": 800}
  ],
  "asks": [
    {"price": 875.40, "qty": 300},
    {"price": 875.60, "qty": 600},
    {"price": 875.85, "qty": 450}
  ],
  "update_time": "2026-04-13T10:30:45"
}
```

## Python SDK Usage

You can also use the moomoo fetcher directly in Python:

```python
from app.data.moomoo_fetcher import (
    fetch_realtime_quote,
    fetch_tick_data,
    fetch_order_book,
    get_moomoo_code
)

# Get real-time quote for NVIDIA
quote = await fetch_realtime_quote("NVDA", "US")
print(f"NVDA last price: ${quote['last_price']}")

# Get tick data for Apple
ticks = await fetch_tick_data("AAPL", "US", num_ticks=100)
print(f"Recent trades: {len(ticks)}")

# Get order book for Maybank
orderbook = await fetch_order_book("MAYBANK", "MY")
print(f"Bid-Ask spread: {orderbook['asks'][0]['price'] - orderbook['bids'][0]['price']}")

# Convert ticker to moomoo code
code = get_moomoo_code("NVDA", "US")  # Returns "US.NVDA"
```

## Caching Strategy

Real-time data is cached with short TTLs:

| Data Type | TTL | Cache Key Format |
|-----------|-----|------------------|
| Real-time quote | 10 seconds | `realtime:{market}:{symbol}` |
| Tick data | Not cached (always fresh) | - |
| Order book | 5 seconds | `orderbook:{market}:{symbol}` |

## Fallback Behavior

If moomoo OpenD is not running or moomoo-api is not installed, the system gracefully falls back to yfinance for basic quote data. This ensures the application continues to function even without real-time data.

## Troubleshooting

### "Failed to connect to moomoo OpenD"

1. Ensure moomoo OpenD gateway is running
2. Check host/port in `.env` matches OpenD settings
3. Verify firewall isn't blocking port 11111

### "No quote data for US.XXXX"

1. Verify the stock symbol is correct for the market
2. Check if you have market data permissions for that market
3. Some Malaysia stocks may have limited real-time data availability

### "moomoo-api not installed"

```bash
pip install moomoo-api
```

## Market Data Requirements

| Market | Subscription Required | Free Tier |
|--------|----------------------|-----------|
| US LV1 | Yes (Nasdaq Basic) | Free with $3,000+ account |
| US LV2 | Yes (TotalView) | Paid subscription |
| Malaysia | Limited | Basic quotes free |
| HK | Yes | Free with active account |

## Resources

- [Official moomoo API Documentation](https://openapi.moomoo.com/moomoo-api-doc/en/)
- [Python SDK GitHub](https://github.com/MoomooOpen/py-moomoo-api)
- [Get Real-time Quote Docs](https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-stock-quote.html)
