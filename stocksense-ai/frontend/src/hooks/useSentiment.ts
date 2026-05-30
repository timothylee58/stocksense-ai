"use client";
import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { SentimentResponse } from "@/types/stock";

export function useSentiment(ticker: string, hours = 24) {
  const [data, setData] = useState<SentimentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (t: string, h: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.sentiment(t, h);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch(ticker, hours);
  }, [ticker, hours, fetch]);

  return { data, loading, error, refetch: () => fetch(ticker, hours) };
}
