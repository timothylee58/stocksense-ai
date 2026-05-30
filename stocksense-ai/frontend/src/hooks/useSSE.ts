"use client";
import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useSSE<T>(ticker: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!ticker) return;

    if (esRef.current) {
      esRef.current.close();
    }

    const es = new EventSource(`${API_URL}/api/stream/${ticker}`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data) as T;
        setData(parsed);
        setError(null);
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setError("SSE connection lost — reconnecting...");
    };

    return () => {
      es.close();
    };
  }, [ticker]);

  return { data, error };
}
