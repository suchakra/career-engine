/**
 * Shared fetch wrapper for the FastAPI backend (AD-16.8).
 *
 * - Attaches the Firebase bearer token to every request (never logged).
 * - Central 401 handling: attempt ONE token refresh; on continued 401, invoke the
 *   registered auth-failure handler (sign out / redirect to login).
 * - Reads the base URL from NEXT_PUBLIC_API_BASE_URL.
 *
 * The token provider and auth-failure handler are injected by the AuthProvider at
 * runtime (configureApiClient), which keeps this module free of a hard Firebase
 * dependency and makes it trivially testable (tests inject a fake token provider).
 */

/** Returns a bearer token, or null when unauthenticated. `forceRefresh` bypasses cache. */
export type TokenProvider = (forceRefresh?: boolean) => Promise<string | null>;

let tokenProvider: TokenProvider = async () => null;
let onAuthFailure: () => void = () => {};

/** Wire the live token source + auth-failure handler (called by AuthProvider). */
export function configureApiClient(opts: {
  getToken: TokenProvider;
  onAuthFailure: () => void;
}): void {
  tokenProvider = opts.getToken;
  onAuthFailure = opts.onAuthFailure;
}

/** Base URL for the backend; falls back to the local Cloud Run-style port. */
export function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";
}

/** Error carrying the HTTP status for typed handling upstream (rollback, toasts). */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function buildHeaders(
  token: string | null,
  hasBody: boolean,
): Promise<Headers> {
  const headers = new Headers();
  if (hasBody) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function parseError(res: Response): Promise<unknown> {
  try {
    return await res.clone().json();
  } catch {
    return undefined;
  }
}

/**
 * Perform a typed JSON request against the backend.
 *
 * @typeParam T - the expected JSON response shape.
 */
export async function apiFetch<T>(
  path: string,
  init: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const url = `${apiBaseUrl()}${path}`;
  const hasBody = init.body !== undefined;
  const serialized = hasBody ? JSON.stringify(init.body) : undefined;

  const doFetch = async (token: string | null): Promise<Response> =>
    fetch(url, {
      method: init.method ?? "GET",
      headers: await buildHeaders(token, hasBody),
      body: serialized,
      signal: init.signal,
    });

  let res = await doFetch(await tokenProvider(false));

  // Central 401 handler: refresh the token once, then retry.
  if (res.status === 401) {
    res = await doFetch(await tokenProvider(true));
    if (res.status === 401) {
      onAuthFailure();
      throw new ApiError(401, "Unauthorized", await parseError(res));
    }
  }

  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, await parseError(res));
  }

  // 204/empty responses return undefined cast to T; JSON responses parse.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
