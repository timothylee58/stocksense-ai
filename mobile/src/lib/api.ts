import Constants from "expo-constants";
import { Platform } from "react-native";

import type {
  DecisionsResponse,
  EquityCurveResponse,
  OrderResponse,
  PortfolioSummary,
  PredictionResponse,
  RejectedResponse,
  Side,
} from "./types";

function resolveBaseUrl(): string {
  const configured = process.env.EXPO_PUBLIC_API_URL?.trim();
  if (configured) return configured.replace(/\/+$/, "");

  if (Platform.OS === "android" && !Constants.expoConfig?.hostUri) {
    return "http://10.0.2.2:8000";
  }

  // Expo Go / dev builds: reach the backend on the same LAN as the dev server.
  const host = Constants.expoConfig?.hostUri?.split(":")[0];
  if (Platform.OS !== "web" && host) return `http://${host}:8000`;

  return "http://localhost:8000";
}

export const API_BASE = resolveBaseUrl();

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25_000);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch (error) {
    clearTimeout(timer);
    const message = error instanceof Error ? error.message : "network error";
    throw new ApiError(
      `Cannot reach ${API_BASE} (${message}). Is the backend running?`,
      0,
      "NETWORK_ERROR",
    );
  }
  clearTimeout(timer);

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (detail && typeof detail === "object") {
      const d = detail as { code?: string; message?: string };
      throw new ApiError(d.message ?? "request failed", response.status, d.code ?? "API_ERROR");
    }
    throw new ApiError(
      typeof detail === "string" ? detail : `HTTP ${response.status}`,
      response.status,
      "API_ERROR",
    );
  }

  return body as T;
}

export const api = {
  summary: () => request<PortfolioSummary>("/api/portfolio/summary"),
  equityCurve: (limit = 200) =>
    request<EquityCurveResponse>(`/api/portfolio/equity-curve?limit=${limit}`),
  rejected: (limit = 25) => request<RejectedResponse>(`/api/portfolio/rejected?limit=${limit}`),
  decisions: (limit = 20) => request<DecisionsResponse>(`/api/trading/decisions?limit=${limit}`),
  prediction: (ticker: string) =>
    request<PredictionResponse>(`/api/predict/${encodeURIComponent(ticker)}`),
  submitOrder: (body: {
    ticker: string;
    side: Side;
    quantity: number;
    price: number;
    order_type: "LIMIT" | "MARKET";
    dry_run: boolean;
    strategy_id: string;
    rationale: string;
    idempotency_key: string;
  }) =>
    request<OrderResponse>("/api/trading/orders", {
      method: "POST",
      headers: { "X-Agent-Id": "mobile-app" },
      body: JSON.stringify(body),
    }),
};
