CREATE TABLE anomalies (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker        TEXT NOT NULL,
  anomaly_score NUMERIC(8,4) NOT NULL,
  is_anomaly    BOOLEAN NOT NULL,
  price_close   NUMERIC(12,4),
  volume        BIGINT,
  daily_return  NUMERIC(8,6),
  bb_width      NUMERIC(8,6),
  volume_zscore NUMERIC(8,4),
  trading_date  DATE NOT NULL,
  detected_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_anomalies_ticker_date ON anomalies (ticker, trading_date DESC);

ALTER TABLE anomalies ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read"    ON anomalies FOR SELECT USING (TRUE);
CREATE POLICY "Service insert" ON anomalies FOR INSERT WITH CHECK (TRUE);
