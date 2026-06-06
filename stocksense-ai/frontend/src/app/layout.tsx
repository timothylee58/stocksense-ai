import type { Metadata } from "next";

import { Space_Mono, Syne } from "next/font/google";

import "./globals.css";

// Syne: geometric, technical — perfect for data dashboards
// Space Mono: monospace for numbers — zero ambiguity on prices

const syne = Syne({
  subsets: ["latin"],
  variable: "--font-syne",
  weight: ["400", "500", "600", "700", "800"],
});

const spaceMono = Space_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "700"],
});

export const metadata: Metadata = {
  title: "StockSense AI — NVDA Intelligence",
  description: "ML-powered NVIDIA stock prediction dashboard using LSTM, XGBoost, and FinBERT sentiment analysis.",
  openGraph: {
    title: "StockSense AI",
    description: "AI-powered NVDA stock prediction",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${syne.variable} ${spaceMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
