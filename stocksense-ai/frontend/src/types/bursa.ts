export interface BursaStock {
  code: string;
  ticker: string;
  name: string;
  sector: string;
  market: string;
  last_price: number;
  open_price: number;
  high_price: number;
  low_price: number;
  prev_close_price: number;
  bid_price: number;
  ask_price: number;
  volume: number;
  change_pct: number;
  change_abs: number;
  source?: string;
  update_time?: string;
}

export interface SectorSnapshot {
  sector: string;
  color: string;
  count: number;
  avg_change: number;
  stocks: string[];
}

export interface MarketSnapshot {
  quotes: BursaStock[];
  gainers: BursaStock[];
  losers: BursaStock[];
  sectors: SectorSnapshot[];
  total: number;
  active: number;
  timestamp: string;
}

export interface BursaPrediction {
  code: string;
  ticker: string;
  direction: "UP" | "DOWN" | "HOLD";
  confidence: number;
  score: number;
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  bb_upper?: number;
  bb_lower?: number;
  current_price?: number;
  momentum_5d?: number;
  momentum_20d?: number;
  vol_ratio?: number;
  signals: string[];
  error?: string;
}
