"use client";
import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { PredictionResponse } from "@/types/stock";

export function usePrediction(ticker: string) {
  const [data, setData] = useState<PredictionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (t: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.predict(t);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch(ticker);
  }, [ticker, fetch]);

  return { data, loading, error, refetch: () => fetch(ticker) };
}
