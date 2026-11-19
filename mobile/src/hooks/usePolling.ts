import { useCallback, useEffect, useRef, useState } from "react";

export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 30_000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const mounted = useRef(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(async (mode: "initial" | "poll" | "refresh") => {
    if (mode === "refresh") setRefreshing(true);
    try {
      const next = await fetcherRef.current();
      if (!mounted.current) return;
      setData(next);
      setError(null);
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      if (!mounted.current) return;
      setLoading(false);
      if (mode === "refresh") setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    load("initial");
    const id = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return;
      load("poll");
    }, intervalMs);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [load, intervalMs]);

  const refresh = useCallback(() => load("refresh"), [load]);

  return { data, error, loading, refreshing, refresh };
}
