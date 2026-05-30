CREATE TABLE sentiment_scores (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker        TEXT NOT NULL,
  finbert_score NUMERIC(5,4) NOT NULL,
  reddit_score  NUMERIC(5,4),
  news_count    INTEGER DEFAULT 0,
  top_headlines JSONB,
  scored_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sentiment_ticker_at ON sentiment_scores (ticker, scored_at DESC);

ALTER TABLE sentiment_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read"    ON sentiment_scores FOR SELECT USING (TRUE);
CREATE POLICY "Service insert" ON sentiment_scores FOR INSERT WITH CHECK (TRUE);
