import { useCallback, useEffect, useRef, useState } from "react";

/** Loads data, and again whenever deps change. Ignores responses that arrive
 * after a newer request has started. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const latest = useRef(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const reload = useCallback(async () => {
    const request = ++latest.current;
    try {
      const result = await load();
      if (request !== latest.current) return;
      setData(result);
      setError("");
    } catch (e) {
      if (request === latest.current) setError((e as Error).message);
    }
  }, deps);

  useEffect(() => {
    void reload();
    return () => {
      latest.current++;
    };
  }, [reload]);

  return { data, error, reload };
}

/** Runs one action at a time, tracking whether it's busy and how it failed. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run };
}

export function useDebounced<T>(value: T, ms = 200): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}
