const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  predict: (ticker: string) =>
    apiFetch<import("@/types/stock").PredictionResponse>(`/api/predict/${ticker}`),

  pipeline: (ticker: string, forceRefresh = false) =>
    apiFetch<import("@/types/stock").PipelineResponse>(
      `/api/predict/${ticker}${forceRefresh ? "?force_refresh=true" : ""}`
    ),

  anomalies: (ticker: string, days = 30) =>
    apiFetch<import("@/types/stock").AnomalyResponse>(
      `/api/anomalies/${ticker}?days=${days}`
    ),

  sentiment: (ticker: string, hours = 24) =>
    apiFetch<import("@/types/stock").SentimentResponse>(
      `/api/sentiment/${ticker}?hours=${hours}`
    ),

  trainTicker: (ticker: string) =>
    apiFetch<{ status: string }>(`/api/train/${ticker}`, { method: "POST" }),

  watchlist: {
    list: () => apiFetch<{ watchlist: string[] }>("/api/watchlist"),
    add: (ticker: string) =>
      apiFetch<{ status: string }>(`/api/watchlist/${ticker}`, { method: "POST" }),
    remove: (ticker: string) =>
      apiFetch<{ status: string }>(`/api/watchlist/${ticker}`, { method: "DELETE" }),
  },
};
