# StockSense AI - Moomoo API Integration Summary

## Overview

This document summarizes the integration of **moomoo API** into StockSense AI, replacing/enhancing the previous Yahoo Finance data pipeline with real-time quotes and tick data for US and Malaysia stocks.

---

## What Changed

### Data Source Comparison

| Feature | Before (yfinance) | After (moomoo) |
|---------|------------------|----------------|
| **Quote Delay** | 15-minute delayed | Real-time (LV1/LV2) |
| **Tick Data** | Not available | Up to 500 recent trades |
| **Order Book** | Not available | Level 2 depth |
| **Malaysia Stocks** | Limited/broken | Supported (MY.{SYMBOL}) |
| **Pre/After Hours** | Limited | Full session data |
| **Update Frequency** | Per-day OHLCV | Millisecond-level ticks |

---

## Files Modified/Created

### New Files

| File | Purpose |
|------|---------|
| `backend/app/data/moomoo_fetcher.py` | Main moomoo API client with quote, tick, and order book methods |
| `backend/.env.example` | Environment variable template with moomoo settings |
| `backend/README_MOOMOO.md` | Detailed setup and usage guide |
| `MOOMOO_INTEGRATION.md` | This summary document |

### Modified Files

| File | Changes |
|------|---------|
| `backend/requirements.txt` | Added `moomoo-api==1.6.0` dependency |
| `backend/app/core/config.py` | Added `moomoo_host`, `moomoo_port`, `moomoo_enabled`, `cache_realtime_ttl` |
| `backend/app/core/stocks.py` | Updated STOCK_UNIVERSE with moomoo market codes (US.*, MY.*) |
| `backend/app/data/fetcher.py` | Added moomoo priority with yfinance fallback |
| `backend/app/api/routes/stocks.py` | Added `/realtime`, `/ticks`, `/orderbook` endpoints |
| `backend/app/core/redis_client.py` | Added `cache_set_typed`, `cache_get_raw` helpers |

---

## New API Endpoints

### Real-Time Quote

```
GET /api/stocks/{ticker}/realtime
```

Returns real-time quote data including last_price, bid/ask, volume, turnover, and pre/after hours prices.

**Example:**
```bash
curl http://localhost:8000/api/stocks/US.NVDA/realtime
```

### Tick Data

```
GET /api/stocks/{ticker}/ticks?num_ticks=100
```

Returns recent tick-by-tick trade data with direction (BUY/SELL) and trade type.

**Example:**
```bash
curl http://localhost:8000/api/stocks/US.AAPL/ticks?num_ticks=50
```

### Order Book (Level 2)

```
GET /api/stocks/{ticker}/orderbook
```

Returns market depth with multiple bid/ask levels.

**Example:**
```bash
curl http://localhost:8000/api/stocks/US.NVDA/orderbook
```

---

## Stock Universe

### US Stocks (Technology)
- `US.AAPL` - Apple Inc.
- `US.NVDA` - NVIDIA Corporation
- `US.MSFT` - Microsoft Corporation
- `US.AMD` - Advanced Micro Devices
- `US.GOOGL` - Alphabet Inc.
- `US.META` - Meta Platforms Inc.

### US Stocks (Other Sectors)
- `US.AMZN` - Amazon.com Inc.
- `US.TSLA` - Tesla Inc.
- `US.WMT` - Walmart Inc.
- `US.NFLX` - Netflix Inc.
- `US.BRK-B` - Berkshire Hathaway
- `US.JPM` - JPMorgan Chase & Co.
- `US.V` - Visa Inc.
- `US.LLY` - Eli Lilly and Company
- `US.XOM` - ExxonMobil Corporation

### Malaysia Stocks (Bursa Malaysia)
- `MY.MAYBANK` - Malayan Banking Berhad
- `MY.TENAGA` - Tenaga Nasional Berhad
- `MY.PETRONAS` - Petronas Chemicals Group
- `MY.PBBANK` - Public Bank Berhad
- `MY.CIMB` - CIMB Group Holdings
- `MY.SIME` - Sime Darby Plantation
- `MY.AXIATA` - Axiata Group Berhad
- `MY.DIGI` - Digi.Com Berhad

---

## Setup Instructions

### 1. Install Dependencies

```bash
cd stocksense-ai/stocksense-ai/backend
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```env
MOOMOO_HOST=127.0.0.1
MOOMOO_PORT=11111
MOOMOO_ENABLED=true
```

### 3. Start moomoo OpenD

1. Download moomoo OpenD from official website
2. Install and launch the gateway client
3. Log in with your moomoo account
4. Verify OpenD is listening on port 11111

### 4. Run StockSense AI Backend

```bash
cd stocksense-ai/stocksense-ai/backend
python -m uvicorn app.main:app --reload --port 8000
```

### 5. Test Real-Time Quote

```bash
curl http://localhost:8000/api/stocks/US.NVDA/realtime
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    StockSense AI Backend                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │   FastAPI    │────▶│  API Router  │────▶│   Stocks    │ │
│  │   (port 800) │     │   /api/*     │     │   Routes    │ │
│  └──────────────┘     └──────────────┘     └──────┬──────┘ │
│                                                    │        │
│                     ┌─────────────────────────────┼────────┐│
│                     │                             │        ││
│              ┌──────▼──────┐            ┌────────▼──────┐ ││
│              │   Moomoo    │            │   yfinance    │ ││
│              │   Fetcher   │            │   (fallback)  │ ││
│              │             │            │               │ ││
│              │ - Quotes    │            │ - Historical  │ ││
│              │ - Ticks     │            │ - OHLCV       │ ││
│              │ - OrderBook │            │               │ ││
│              └──────┬──────┘            └───────────────┘ ││
│                     │                                      ││
│              ┌──────▼──────┐                               ││
│              │   moomoo    │                               ││
│              │   OpenD     │                               ││
│              │  (127.0.0.1 │                               ││
│              │   :11111)   │                               ││
│              └─────────────┘                               ││
│                                                            ││
│  ┌──────────────────────────────────────────────────────┐ ││
│  │                    Redis Cache                        │ ││
│  │  - realtime:{market}:{symbol} (10s TTL)              │ ││
│  │  - dataset:{ticker}:{period}y (15min TTL)            │ ││
│  └──────────────────────────────────────────────────────┘ ││
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## Caching Strategy

| Data Type | Cache Key | TTL | Notes |
|-----------|-----------|-----|-------|
| Real-time quote | `realtime:{market}:{symbol}` | 10 seconds | Fresh prices |
| Historical dataset | `dataset:{ticker}:{period}y` | 15 minutes | OHLCV + indicators |
| Order book | `orderbook:{market}:{symbol}` | 5 seconds | Rapid changes |
| Tick data | Not cached | N/A | Always fresh |

---

## Fallback Behavior

The system implements graceful degradation:

1. **moomoo enabled + connected** → Use moomoo for all data
2. **moomoo enabled but disconnected** → Log warning, fall back to yfinance
3. **moomoo disabled** → Use yfinance only
4. **moomoo-api not installed** → Log warning, use yfinance only

This ensures StockSense AI continues functioning even without moomoo OpenD running.

---

## Code Examples

### Python SDK Usage

```python
from app.data.moomoo_fetcher import (
    fetch_realtime_quote,
    fetch_tick_data,
    fetch_order_book,
    get_moomoo_code
)

# Real-time quote
quote = await fetch_realtime_quote("NVDA", "US")
print(f"NVDA: ${quote['last_price']:.2f}")

# Tick data
ticks = await fetch_tick_data("AAPL", "US", num_ticks=100)
print(f"Recent trades: {len(ticks)}")

# Order book
ob = await fetch_order_book("MAYBANK", "MY")
spread = ob['asks'][0]['price'] - ob['bids'][0]['price']
print(f"Bid-Ask spread: {spread:.4f}")

# Market code conversion
code = get_moomoo_code("NVDA", "US")  # "US.NVDA"
```

### Frontend Integration (React/Next.js)

```typescript
// Fetch real-time quote
async function getRealtimeQuote(ticker: string) {
  const res = await fetch(`/api/stocks/${ticker}/realtime`);
  return res.json();
}

// Poll for updates every 10 seconds
useEffect(() => {
  const interval = setInterval(async () => {
    const quote = await getRealtimeQuote('US.NVDA');
    setPrice(quote.last_price);
  }, 10000);
  return () => clearInterval(interval);
}, []);
```

---

## Testing

### Test Real-Time Quote Endpoint

```bash
curl -s http://localhost:8000/api/stocks/US.AAPL/realtime | jq
```

### Test Tick Data

```bash
curl -s "http://localhost:8000/api/stocks/US.NVDA/ticks?num_ticks=20" | jq
```

### Test Order Book

```bash
curl -s http://localhost:8000/api/stocks/US.MSFT/orderbook | jq
```

### Test Malaysia Stock

```bash
curl -s http://localhost:8000/api/stocks/MY.MAYBANK/realtime | jq
```

---

## Known Limitations

1. **moomoo OpenD Required**: Must run locally on the same machine
2. **Market Data Subscription**: LV2 data requires paid subscription
3. **Malaysia Data**: Some MY stocks may have delayed/limited real-time data
4. **Account Assets**: Free LV1 requires $3,000+ account balance

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Ensure moomoo OpenD is running |
| No data for symbol | Verify market code format (US.AAPL, MY.MAYBANK) |
| Module not found | `pip install moomoo-api` |
| Permission denied | Check moomoo account has market data rights |

---

## Resources

- [moomoo API Documentation](https://openapi.moomoo.com/moomoo-api-doc/en/)
- [Python SDK GitHub](https://github.com/MoomooOpen/py-moomoo-api)
- [Real-Time Quote Guide](https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-stock-quote.html)
- [Subscription Guide](https://openapi.moomoo.com/moomoo-api-doc/en/quote/sub.html)

---

## Next Steps

1. **WebSocket Streaming**: Implement real-time push notifications for price updates
2. **Historical Backfill**: Use moomoo K-line data for full historical datasets
3. **Options/Futures**: Add derivatives data support
4. **Market Scanner**: Build real-time screener using tick data
5. **Alert System**: Price alerts based on real-time quotes

---

**Integration Date**: 2026-04-13  
**Version**: 1.0.0  
**Author**: StockSense AI Team
