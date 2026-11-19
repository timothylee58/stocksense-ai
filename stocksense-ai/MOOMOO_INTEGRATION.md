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

### 3. Start moomoo OpenD (macOS, paper trading)

OpenD is the local gateway the Python SDK talks to. It must stay running while the backend trades; the backend fails closed (`503 PAPER_ACCOUNT_ID_REQUIRED` / `BROKER_UNAVAILABLE`) when it is down.

1. **Download** the macOS build from <https://www.moomoo.com/download/OpenAPI> (`opend-macos`).
2. **Unzip** and either launch `OpenD.app` or run it from a terminal:
   ```bash
   ./OpenD.app/Contents/MacOS/OpenD
   ```
   > macOS gives the app a random working directory at launch. If it cannot find its config, pass it explicitly: `OpenD -cfg_file=/absolute/path/OpenD.xml` (the CLI tarball also ships `fixrun.sh` for this).
3. **Log in** with your moomoo ID (or `+country-code` phone number) and password, plus the OTP if prompted. From v10.10 OpenD starts in interactive login mode.
4. **Confirm the gateway is listening** (default `127.0.0.1:11111`):
   ```bash
   nc -z 127.0.0.1 11111 && echo "OpenD up"
   lsof -nP -iTCP:11111 -sTCP:LISTEN
   ```
5. **Create the paper account once** if you have never used it: moomoo desktop app → left sidebar **Paper**, or mobile → **Me → Paper Trading**. All four platforms (app, desktop, web, API) share the same paper accounts.
6. **Find the SIMULATE `acc_id`** with the repo's virtualenv:
   ```bash
   cd stocksense-ai/stocksense-ai/backend && .venv/bin/python - <<'PY'
   import moomoo as sdk
   from app.core.config import get_settings
   s = get_settings()
   ctx = sdk.OpenSecTradeContext(
       filter_trdmarket=getattr(sdk.TrdMarket, s.moomoo_trd_market.upper()),
       host=s.moomoo_host, port=s.moomoo_port,
       security_firm=getattr(sdk.SecurityFirm, s.moomoo_security_firm.upper()),
   )
   ret, data = ctx.get_acc_list()
   print(data[["acc_id", "trd_env", "acc_type", "sim_acc_type", "trdmarket_auth", "acc_status"]])
   ctx.close()
   PY
   ```
   Pick the row where `trd_env == SIMULATE`, `trdmarket_auth` contains `US`, `sim_acc_type` is `STOCK_AND_OPTION` (US margin paper account), and `acc_status` is `ACTIVE`. `sim_acc_type=OPTION` / `FUTURES` accounts cannot trade stocks; `FUTURES_SIMULATE_*` rows belong to `OpenFutureTradeContext`.
7. **Configure the backend** `backend/.env`:
   ```env
   DEMO_MODE=false
   MOOMOO_ENABLED=true
   MOOMOO_TRADE_ENABLED=true
   MOOMOO_TRD_ENV=SIMULATE
   MOOMOO_PAPER_ACCOUNT_ID=<acc_id from step 6>
   MOOMOO_TRD_MARKET=US
   MOOMOO_SECURITY_FIRM=FUTUSECURITIES
   ```
8. **Verify the guard** after starting the backend:
   ```bash
   curl -s http://localhost:8000/api/trading/account | jq
   ```
   `verified` must be `true` and `source` must be `moomoo`; the endpoint never returns live account data.

> Paper trading does not require an account unlock/trade password in the SDK. Live environments are rejected by `verify_paper_guard()` before any SDK call.

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
| `503 PAPER_ACCOUNT_ID_REQUIRED` | `MOOMOO_PAPER_ACCOUNT_ID` is empty — run the `get_acc_list` snippet above |
| `PAPER_ACCOUNT_NOT_FOUND` | The `acc_id` does not match the account OpenD is logged into, or `trd_env` is not SIMULATE |
| No SIMULATE row in `get_acc_list` | Create the paper account in the moomoo app (Me → Paper Trading); HK paper accounts need `filter_trdmarket=TrdMarket.HK` |
| "The current securities account has not yet agreed to the disclaimer" | Accept the risk disclosure for your firm (e.g. [Moomoo SG](https://risk-disclosure.sg.moomoo.com/index?agreementNo=SGOT0015), [Moomoo MY](https://risk-disclosure.my.moomoo.com/index?agreementNo=MYOT0066)) and restart OpenD |
| Order intercepted as Pattern Day Trader | US accounts: 4th day trade in 5 sessions is blocked by default; set `pdt_protection=0` in `OpenD.xml` only if you accept PDT rules |

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
