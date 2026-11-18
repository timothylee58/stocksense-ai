export type Side = "BUY" | "SELL";

export interface AccountStatus {
  verified: boolean;
  source: string;
  trd_env: string;
  account_id: string;
  currency: string;
  equity: number;
  cash: number;
  market_value: number;
}

export interface Position {
  ticker: string;
  quantity: number;
  market_value: number;
  allocation_pct?: number;
}

export interface PortfolioSnapshot {
  account_id: string;
  equity: number;
  cash: number;
  day_pnl: number;
  peak_equity: number;
  positions: Position[];
}

export interface LedgerStats {
  total_events: number;
  decisions: number;
  approved: number;
  rejected: number;
  executions: number;
  filled: number;
  dry_run: number;
  failed: number;
  duplicate_blocked: number;
}

export interface PortfolioSummary {
  generated_at: string;
  demo: boolean;
  account: AccountStatus;
  summary: {
    equity: number;
    cash: number;
    market_value: number;
    day_pnl: number;
    day_pnl_pct: number;
    baseline_equity: number;
    total_pnl: number;
    total_return_pct: number;
    gross_exposure_pct: number;
    position_count: number;
    kill_switch_active: boolean;
    snapshot_storage: string;
  };
  positions: Position[];
  kill_switch: { enabled: boolean; reason: string | null; actor: string | null; updated_at: string | null };
  ledger: LedgerStats;
}

export interface EquityPoint {
  snapshot_id: string;
  account_id: string;
  source: string;
  equity: number;
  cash: number;
  market_value: number;
  day_pnl: number;
  gross_exposure_pct: number;
  position_count: number;
  kill_switch_active: boolean;
  captured_at: string;
}

export interface EquityCurveResponse {
  count: number;
  points: EquityPoint[];
}

export interface LedgerRecord {
  decision_id: string;
  event_type: "decision" | "execution";
  status: string;
  account_id: string;
  ticker: string;
  side: Side;
  quantity: number;
  price: number;
  notional: number;
  dry_run?: number | boolean;
  reason_codes: string[] | string;
  order_id?: string;
  message?: string;
  strategy_id?: string;
  actor?: string;
  event_time: string;
}

export interface RejectedResponse {
  count: number;
  rejections: LedgerRecord[];
}

export interface DecisionsResponse {
  count: number;
  decisions: LedgerRecord[];
}

export interface RiskCheck {
  name: string;
  passed: boolean;
  code: string;
  detail: string;
}

export interface OrderDecision {
  decision_id: string;
  approved: boolean;
  reason_codes: string[];
  checks: RiskCheck[];
  order: {
    ticker: string;
    side: Side;
    quantity: number;
    price: number;
    order_type: string;
    dry_run: boolean;
    strategy_id: string;
    rationale: string;
    idempotency_key: string;
    model_version: string;
  };
  account_id: string;
  kill_switch_active: boolean;
  notional: number;
  projected_position_pct: number;
  projected_gross_pct: number;
  cash_after: number;
  day_pnl_pct: number;
  drawdown_pct: number;
  evaluated_at: string;
}

export interface OrderExecution {
  status: "submitted" | "filled" | "dry_run" | "duplicate_blocked" | "failed" | "rejected";
  order_id?: string;
  message: string;
  dry_run: boolean;
  executed_at: string;
}

export interface OrderResponse {
  decision: OrderDecision;
  execution?: OrderExecution;
  ledger?: string;
  ledger_execution?: string;
}

export interface PredictionResponse {
  ticker: string;
  name: string;
  sector: string;
  current_price: number;
  forecast_price: number;
  signal: Side | "HOLD";
  confidence: number;
  sentiment_score: number;
  trend: "BULLISH" | "BEARISH" | "SIDEWAYS";
  price_target_7d: number;
  price_target_14d: number;
  price_target_30d: number;
  price_change_pct: number;
  rsi: number | null;
  macd: number | null;
  bollinger_upper: number | null;
  bollinger_lower: number | null;
  sma_20: number | null;
  sma_50: number | null;
  chart_data: { time: string; price: number }[];
}
