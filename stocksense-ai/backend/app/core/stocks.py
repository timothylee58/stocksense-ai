import math

# Top US stocks — market cap leaders + famous names
# Moomoo market code format: US.{TICKER} for US stocks, MY.{TICKER} for Malaysia stocks
STOCK_UNIVERSE: dict[str, dict] = {
    # US Technology
    "US.AAPL":  {"name": "Apple Inc.",             "sector": "Technology",   "market": "US"},
    "US.NVDA":  {"name": "NVIDIA Corporation",     "sector": "Technology",   "market": "US"},
    "US.MSFT":  {"name": "Microsoft Corporation",  "sector": "Technology",   "market": "US"},
    "US.AMD":   {"name": "Advanced Micro Devices", "sector": "Technology",   "market": "US"},
    "US.GOOGL": {"name": "Alphabet Inc.",          "sector": "Communication","market": "US"},
    "US.META":  {"name": "Meta Platforms Inc.",    "sector": "Communication","market": "US"},

    # US Consumer
    "US.AMZN":  {"name": "Amazon.com Inc.",        "sector": "Consumer Cyclical", "market": "US"},
    "US.TSLA":  {"name": "Tesla Inc.",             "sector": "Consumer Cyclical", "market": "US"},
    "US.WMT":   {"name": "Walmart Inc.",           "sector": "Consumer Defensive","market": "US"},
    "US.NFLX":  {"name": "Netflix Inc.",           "sector": "Communication",  "market": "US"},

    # US Financials
    "US.BRK-B": {"name": "Berkshire Hathaway",     "sector": "Financials",     "market": "US"},
    "US.JPM":   {"name": "JPMorgan Chase & Co.",   "sector": "Financials",     "market": "US"},
    "US.V":     {"name": "Visa Inc.",              "sector": "Financials",     "market": "US"},

    # US Healthcare & Energy
    "US.LLY":   {"name": "Eli Lilly and Company",  "sector": "Healthcare",     "market": "US"},
    "US.XOM":   {"name": "ExxonMobil Corporation", "sector": "Energy",         "market": "US"},

    # ── Malaysia Stocks (Bursa Malaysia / KLSE) ───────────────────────────────
    # Financials
    "MY.MAYBANK":  {"name": "Malayan Banking Berhad",   "sector": "Financials",          "market": "MY", "klse_code": "1155"},
    "MY.PBBANK":   {"name": "Public Bank Berhad",        "sector": "Financials",          "market": "MY", "klse_code": "1295"},
    "MY.CIMB":     {"name": "CIMB Group Holdings",       "sector": "Financials",          "market": "MY", "klse_code": "1023"},
    "MY.RHBBANK":  {"name": "RHB Bank Berhad",           "sector": "Financials",          "market": "MY", "klse_code": "1066"},
    "MY.HLBANK":   {"name": "Hong Leong Bank Berhad",    "sector": "Financials",          "market": "MY", "klse_code": "5819"},
    # Utilities / Energy
    "MY.TENAGA":   {"name": "Tenaga Nasional Berhad",    "sector": "Utilities",           "market": "MY", "klse_code": "5347"},
    "MY.PETGAS":   {"name": "Petronas Gas Berhad",       "sector": "Utilities",           "market": "MY", "klse_code": "6033"},
    "MY.YTLPOWR":  {"name": "YTL Power International",   "sector": "Utilities",           "market": "MY", "klse_code": "6742"},
    # Materials / Industrials
    "MY.PETRONAS": {"name": "Petronas Chemicals Group",  "sector": "Materials",           "market": "MY", "klse_code": "5183"},
    "MY.HAPSENG":  {"name": "Hap Seng Consolidated",     "sector": "Industrials",         "market": "MY", "klse_code": "3034"},
    "MY.GAMUDA":   {"name": "Gamuda Berhad",             "sector": "Industrials",         "market": "MY", "klse_code": "5398"},
    # Communication / Technology
    "MY.AXIATA":   {"name": "Axiata Group Berhad",       "sector": "Communication",       "market": "MY", "klse_code": "6888"},
    "MY.MAXIS":    {"name": "Maxis Berhad",              "sector": "Communication",       "market": "MY", "klse_code": "6012"},
    "MY.DIGI":     {"name": "CelcomDigi Berhad",         "sector": "Communication",       "market": "MY", "klse_code": "6947"},
    # Healthcare
    "MY.IHH":      {"name": "IHH Healthcare Berhad",     "sector": "Healthcare",          "market": "MY", "klse_code": "5225"},
    # Consumer
    "MY.SIME":     {"name": "Sime Darby Plantation",     "sector": "Consumer Defensive",  "market": "MY", "klse_code": "5285"},
    "MY.GENTING":  {"name": "Genting Berhad",            "sector": "Consumer Cyclical",   "market": "MY", "klse_code": "3182"},
}

# yfinance ticker map for Malaysian stocks (KLSE code + ".KL")
MY_YF_TICKERS: dict[str, str] = {
    k: f"{v['klse_code']}.KL"
    for k, v in STOCK_UNIVERSE.items()
    if v.get("market") == "MY" and "klse_code" in v
}

# moomoo addresses Bursa stocks by numeric KLSE code (MY.1155), not by name.
MY_KLSE_CODES: dict[str, str] = {
    k.split(".", 1)[1]: v["klse_code"]
    for k, v in STOCK_UNIVERSE.items()
    if v.get("market") == "MY" and "klse_code" in v
}

# Short names → SGX codes; moomoo addresses SG stocks as SG.<code> (SG.D05).
SGX_CODES: dict[str, str] = {
    "DBS":          "D05",
    "UOB":          "U11",
    "OCBC":         "O39",
    "SINGTEL":      "Z74",
    "SIA":          "C6L",
    "SGX":          "S68",
    "STENG":        "S63",
    "CAPITALAND":   "9CI",
    "KEPPEL":       "BN4",
    "WILMAR":       "F34",
    "THAIBEV":      "Y92",
    "SATS":         "S58",
    "SEMBCORP":     "U96",
    "COMFORTDELGRO": "C52",
    "VENTURE":      "V03",
    "CDL":          "C09",
}


def get_security_code(ticker: str, market: str = "US") -> str:
    """Exchange-native symbol moomoo expects (KLSE number for MY, SGX code for SG)."""
    symbol = ticker.upper()
    if "." in symbol:
        symbol = symbol.split(".", 1)[1]
    market = market.upper()
    if market == "MY":
        return MY_KLSE_CODES.get(symbol, symbol)
    if market == "SG":
        return SGX_CODES.get(symbol, symbol)
    return symbol


# Sub-cent values are corrupt feed artifacts, not quotes (e.g. yfinance resolving
# the MY ticker "DIGI" to a $0.0001 OTC shell).
MIN_VALID_PRICE = 0.01


def valid_price(value) -> float:
    """Coerce to a finite, plausible price; 0.0 means missing/corrupt."""
    try:
        price = float(value)
    except (TypeError, ValueError):
        return 0.0
    return price if math.isfinite(price) and price >= MIN_VALID_PRICE else 0.0


def get_stock_info(ticker: str) -> dict:
    return STOCK_UNIVERSE.get(ticker.upper(), {
        "name": ticker.upper(),
        "sector": "Unknown",
    })


def get_all_tickers() -> list[str]:
    return list(STOCK_UNIVERSE.keys())


def get_my_tickers() -> list[str]:
    return [k for k, v in STOCK_UNIVERSE.items() if v.get("market") == "MY"]

