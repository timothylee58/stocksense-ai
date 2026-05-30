"use client";
import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { AnomalyResponse } from "@/types/stock";

export function useAnomalies(ticker: string, days = 30) {
  const [data, setData] = useState<AnomalyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (t: string, d: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.anomalies(t, d);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch(ticker, days);
  }, [ticker, days, fetch]);

  return { data, loading, error, refetch: () => fetch(ticker, days) };
}
