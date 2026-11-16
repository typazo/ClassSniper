import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { MajorMode, PrereqCourseOption } from "../types";

export function usePrereqOptions(
  roster: string,
  query: string,
  mode: MajorMode | "general",
  options?: {
    enabled?: boolean;
    allowEmptyQuery?: boolean;
    limit?: number;
    debounceMs?: number;
  }
) {
  const enabled = options?.enabled ?? true;
  const allowEmptyQuery = options?.allowEmptyQuery ?? false;
  const limit = options?.limit ?? 15;
  const debounceMs = options?.debounceMs ?? 150;

  const [results, setResults] = useState<PrereqCourseOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (!enabled || !roster || (!allowEmptyQuery && !q)) {
      setResults([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    const handle = window.setTimeout(() => {
      api
        .getPrereqOptions(roster, q, limit, mode)
        .then((res) => {
          if (!cancelled) setResults(res.options);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, debounceMs);

    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [roster, query, mode, enabled, allowEmptyQuery, limit, debounceMs]);

  return { options: results, loadingOptions: loading, setOptions: setResults };
}
