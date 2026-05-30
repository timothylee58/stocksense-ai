export const STOCKS = [
  { ticker: "NVDA",       name: "NVIDIA",        sector: "Technology" },
  { ticker: "AAPL",       name: "Apple",          sector: "Technology" },
  { ticker: "MSFT",       name: "Microsoft",      sector: "Technology" },
  { ticker: "AMZN",       name: "Amazon",         sector: "Consumer" },
  { ticker: "GOOGL",      name: "Alphabet",       sector: "Communication" },
  { ticker: "META",       name: "Meta",           sector: "Communication" },
  { ticker: "TSLA",       name: "Tesla",          sector: "Automotive" },
  { ticker: "JPM",        name: "JPMorgan",       sector: "Financials" },
  { ticker: "MAYBANK.KL", name: "Maybank",        sector: "Finance (MY)" },
  { ticker: "PBBANK.KL",  name: "Public Bank",    sector: "Finance (MY)" },
] as const;

export const REFRESH_INTERVAL_MS = 30_000; // 30 seconds
export const ANOMALY_DAYS_DEFAULT = 30;
export const SENTIMENT_HOURS_DEFAULT = 24;

export const SIG_COLOR: Record<string, string> = {
  BUY: "#00ffcc",
  SELL: "#ff4560",
  HOLD: "#f5a623",
};

export const RISK_COLOR: Record<string, string> = {
  LOW: "#00ffcc",
  MEDIUM: "#f5a623",
  HIGH: "#ff4560",
};
