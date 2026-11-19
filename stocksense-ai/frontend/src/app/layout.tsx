import type { Metadata } from "next";

import { Space_Mono } from "next/font/google";

import "./globals.css";

// Space Mono keeps financial figures unambiguous; display type is a serif system stack.

const spaceMono = Space_Mono({
  subsets: ["latin"],
  variable: "--font-space-mono",
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
    <html lang="en" className={spaceMono.variable}>
      <body>{children}</body>
    </html>
  );
}
