import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPrice(v: number | null | undefined): string {
  if (v == null) return "—";
  return "$" + v.toFixed(2);
}

export function formatPct(v: number): string {
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
}

export function formatScore(v: number): string {
  return (v >= 0 ? "+" : "") + v.toFixed(3);
}

export function sentimentLabel(score: number): string {
  if (score > 0.2) return "Bullish";
  if (score < -0.2) return "Bearish";
  return "Neutral";
}

export function sentimentColor(score: number): string {
  if (score > 0.2) return "#00ffcc";
  if (score < -0.2) return "#ff4560";
  return "#f5a623";
}
