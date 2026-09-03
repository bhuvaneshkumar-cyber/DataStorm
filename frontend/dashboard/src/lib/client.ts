/**
 * The one place this app talks to a network.
 *
 * Two services sit behind it: the financial engine (auth, money, loans, tax,
 * bot) and the scoring service (statement upload, corporate financials). Both
 * are reached through the same `request` helper so that bearer tokens, error
 * unwrapping and timeouts behave identically no matter which one answers.
 *
 * Base URLs come from Vite env vars (see .env.example) so nothing here breaks
 * when the app is deployed off localhost.
 */

const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000').replace(/\/$/, '');
const ML_URL = (import.meta.env.VITE_ML_URL ?? 'http://localhost:8001').replace(/\/$/, '');

/**
 * Where the session lives.
 *
 * localStorage rather than a cookie: the API is a separate origin and is called
 * with an Authorization header, so there is no cookie for a browser to attach
 * anyway. The trade is that the token is readable by any script on this origin,
 * which is why the app ships no third-party scripts.
 */
const TOKEN_KEY = 'gigsave.token';

/** A request that never returns is worse than one that fails; nothing waits forever. */
const TIMEOUT_MS = 30_000;
const UPLOAD_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }

  /** True when the session is missing or expired, which the app handles by signing out. */
  get isUnauthenticated() {
    return this.status === 401;
  }

  /** True when a dependency is down rather than the request being wrong. */
  get isUnavailable() {
    return this.status === 503 || this.status === 0;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    // Private mode, or storage disabled. Treated as "not signed in" rather than
    // crashing the app on first paint.
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing to do: the session simply will not survive a reload.
  }
}

/** Callbacks fired when the server rejects our token, so the app can sign out. */
const expiryListeners = new Set<() => void>();

export function onSessionExpired(listener: () => void): () => void {
  expiryListeners.add(listener);
  return () => expiryListeners.delete(listener);
}

/**
 * Turns a failed response into an Error carrying the server's own explanation.
 *
 * FastAPI puts the reason in `detail`, either as a string or as a list of
 * per-field validation errors. Both are unwrapped here so no caller has to, and
 * so the UI can show "amount must be greater than 0" instead of "HTTP 422".
 */
async function toError(response: Response, fallback: string): Promise<ApiError> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === 'string' && detail) return new ApiError(detail, response.status);
    if (Array.isArray(detail) && detail.length) {
      const message = detail
        .map((item: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : '';
          return field ? `${field}: ${item.msg}` : item.msg;
        })
        .join('; ');
      return new ApiError(message, response.status);
    }
  } catch {
    // Body was not JSON: a proxy error page, or an empty 502. Fall through.
  }
  return new ApiError(`${fallback} (HTTP ${response.status})`, response.status);
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  /** Multipart uploads must not have Content-Type set by hand: see below. */
  form?: FormData;
  auth?: boolean;
  fallback?: string;
  signal?: AbortSignal;
};

async function request<T>(base: string, path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = 'GET',
    body,
    form,
    auth = true,
    fallback = 'That request could not be completed',
    signal,
  } = options;

  const headers: Record<string, string> = {};
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  // Content-Type is deliberately unset for FormData: the browser must add the
  // multipart boundary itself, and setting it by hand produces a request the
  // server cannot parse.
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    form ? UPLOAD_TIMEOUT_MS : TIMEOUT_MS,
  );
  // Caller-supplied cancellation (a component unmounting) and our own timeout
  // both have to reach the same fetch.
  signal?.addEventListener('abort', () => controller.abort(), { once: true });

  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      method,
      headers,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal: controller.signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error; // the caller cancelled; not a failure to report
    // Status 0 marks "never reached the server" so callers can say "service
    // unreachable" rather than inventing a status code.
    throw new ApiError(
      controller.signal.aborted
        ? 'That request took too long and was cancelled.'
        : `${fallback}: the service is unreachable.`,
      0,
    );
  } finally {
    window.clearTimeout(timeout);
  }

  if (response.status === 401 && auth) {
    expiryListeners.forEach((listener) => listener());
  }

  if (!response.ok) throw await toError(response, fallback);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const backend = <T>(path: string, options?: RequestOptions) =>
  request<T>(BACKEND_URL, path, options);

export const scoring = <T>(path: string, options?: RequestOptions) =>
  request<T>(ML_URL, path, options);
