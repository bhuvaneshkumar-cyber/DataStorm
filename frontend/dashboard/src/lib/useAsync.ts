/**
 * One data-fetching hook for the whole app.
 *
 * Every screen here does the same thing: call an endpoint, show a spinner, show
 * the server's message if it fails, offer a retry. Written once, that is a hook;
 * written per page, it is fourteen slightly different loading states, three of
 * which forget to handle the error.
 *
 * ponytail: no cache and no request dedupe. Add TanStack Query the day two
 * screens need to share one response and stay in step.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from './client';

export type AsyncState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** True when the failure was a service being down rather than a bad request. */
  unavailable: boolean;
  reload: () => void;
};

export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  // The loader is usually an inline arrow function, so it is a new value every
  // render. Holding it in a ref keeps it out of the effect's dependencies, which
  // is what stops the fetch from looping forever.
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setUnavailable(false);

    loaderRef
      .current()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setUnavailable(cause instanceof ApiError && cause.isUnavailable);
        setError(cause instanceof Error ? cause.message : 'Something went wrong.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return { data, error, loading, unavailable, reload };
}

/**
 * The mutation counterpart: run an action, track whether it is in flight, and
 * surface the server's own message when it fails.
 */
export function useAction<Args extends unknown[], Result>(
  action: (...args: Args) => Promise<Result>,
) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (...args: Args): Promise<Result | null> => {
      setBusy(true);
      setError(null);
      try {
        return await action(...args);
      } catch (cause: unknown) {
        setError(cause instanceof Error ? cause.message : 'Something went wrong.');
        return null;
      } finally {
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  return { run, busy, error, clearError: useCallback(() => setError(null), []) };
}
