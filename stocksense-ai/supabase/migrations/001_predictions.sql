CREATE TABLE predictions (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker        TEXT NOT NULL,
  signal        TEXT NOT NULL CHECK (signal IN ('BUY', 'SELL', 'HOLD')),
  confidence    NUMERIC(5,4) NOT NULL,
  direction     TEXT NOT NULL CHECK (direction IN ('UP', 'DOWN', 'NEUTRAL')),
  xgb_prob_up   NUMERIC(5,4),
  lr_prob_up    NUMERIC(5,4),
  is_anomaly    BOOLEAN DEFAULT FALSE,
  anomaly_score NUMERIC(8,4),
  model_version TEXT,
  predicted_at  TIMESTAMPTZ DEFAULT NOW(),
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_predictions_ticker_at ON predictions (ticker, predicted_at DESC);

ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read"   ON predictions FOR SELECT USING (TRUE);
CREATE POLICY "Service insert" ON predictions FOR INSERT WITH CHECK (TRUE);
