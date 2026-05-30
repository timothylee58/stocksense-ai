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

    # Malaysia Stocks (Top companies on Bursa Malaysia)
    "MY.MAYBANK": {"name": "Malayan Banking Berhad",    "sector": "Financials", "market": "MY"},
    "MY.TENAGA":  {"name": "Tenaga Nasional Berhad",    "sector": "Utilities",  "market": "MY"},
    "MY.PETRONAS": {"name": "Petronas Chemicals Group", "sector": "Materials",  "market": "MY"},
    "MY.PBBANK":  {"name": "Public Bank Berhad",        "sector": "Financials", "market": "MY"},
    "MY.CIMB":    {"name": "CIMB Group Holdings",       "sector": "Financials", "market": "MY"},
    "MY.SIME":    {"name": "Sime Darby Plantation",     "sector": "Consumer Defensive", "market": "MY"},
    "MY.AXIATA":  {"name": "Axiata Group Berhad",       "sector": "Communication", "market": "MY"},
    "MY.DIGI":    {"name": "Digi.Com Berhad",           "sector": "Communication", "market": "MY"},
}


def get_stock_info(ticker: str) -> dict:
    return STOCK_UNIVERSE.get(ticker.upper(), {
        "name": ticker.upper(),
        "sector": "Unknown",
    })


def get_all_tickers() -> list[str]:
    return list(STOCK_UNIVERSE.keys())
