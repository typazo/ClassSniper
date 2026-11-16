import { useCallback, useEffect, useRef, useState } from "react";
import { copyText } from "../utils/pwa";

export function useCopyFeedback<K extends string | number = string>(timeoutMs = 1800) {
  const [copiedKey, setCopiedKey] = useState<K | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }
    };
  }, []);

  const copy = useCallback(
    async (text: string, key: K = "default" as K): Promise<boolean> => {
      const ok = await copyText(text);
      if (ok) {
        setCopiedKey(key);
        if (timerRef.current !== null) {
          window.clearTimeout(timerRef.current);
        }
        timerRef.current = window.setTimeout(() => {
          setCopiedKey(null);
          timerRef.current = null;
        }, timeoutMs);
      }
      return ok;
    },
    [timeoutMs]
  );

  const reset = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setCopiedKey(null);
  }, []);

  return { copiedKey, copy, reset };
}
