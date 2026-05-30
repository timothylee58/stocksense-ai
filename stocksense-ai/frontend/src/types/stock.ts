export interface StockData {
  time: string;
  price: number;
  predicted?: number;
}

export interface ForecastPoint {
  date: string;
  price: number;
  lower: number;
  upper: number;
}

export interface TimingAnalysis {
  timing_score: number;            // 0–10
  action: 'BUY_NOW' | 'WAIT_FOR_DIP' | 'HOLD' | 'SELL_NOW' | 'AVOID';
  buy_zone_low: number;
  buy_zone_high: number;
  stop_loss: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
  days_to_opportunity: number | null;
  rationale: string[];
}

export interface PredictionResponse {
  ticker: string;
  name: string;
  sector: string;
  current_price: number;
  forecast_price: number;          // 7-day target
  signal: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  sentiment_score: number;
  trend: 'BULLISH' | 'BEARISH' | 'SIDEWAYS';
  price_target_7d: number;
  price_target_14d: number;
  price_target_30d: number;
  price_change_pct: number;
  timing: TimingAnalysis;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  bollinger_upper: number | null;
  bollinger_lower: number | null;
  sma_20: number | null;
  sma_50: number | null;
  chart_data: StockData[];
  forecast_data: ForecastPoint[];
}

export interface StockInfo {
  ticker: string;
  name: string;
  sector: string;
}

export interface AnomalyRecord {
  ticker: string;
  trading_date: string;
  anomaly_score: number;
  is_anomaly: boolean;
  price_close: number;
  volume: number;
  daily_return: number | null;
  bb_width: number | null;
  volume_zscore: number | null;
}

export interface AnomalyResponse {
  ticker: string;
  days: number;
  records: AnomalyRecord[];
  source: 'database' | 'computed';
}

export interface HeadlineItem {
  title: string;
  source: string;
  url: string;
  score?: number;
}

export interface SentimentResponse {
  ticker: string;
  finbert_score: number;      // -1 to 1
  reddit_score: number | null;
  news_count: number;
  top_headlines: HeadlineItem[];
  scored_at: string | null;
  source: 'database' | 'computed';
}

export interface PipelineResponse {
  ticker: string;
  current_price: number;
  signal: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  xgb_prob_up: number;
  xgb_prob_down: number;
  is_anomaly: boolean;
  anomaly_score: number;
  finbert_score: number;
  reddit_sentiment: number;
  news_volume: number;
  top_headlines: HeadlineItem[];
}
