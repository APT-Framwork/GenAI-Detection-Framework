/**
 * Bearer-token fetch wrapper for the STRIX mobile app.
 *
 * Matches the backend's §13 Problem+JSON envelope and the M0 auth
 * contract:
 *   - every request sets `X-Client-Type: mobile` (tells the API we want
 *     the refresh token in the response body, not a cookie)
 *   - every request carries the current access token as `Authorization:
 *     Bearer <jwt>`
 *   - on 401, we transparently refresh via POST /auth/refresh (body
 *     contains the refresh token) and retry the original request once.
 *     Refresh calls are single-flight: concurrent 401s wait on the same
 *     promise so we don't race.
 *
 * Errors are thrown as `StrixApiError` so callers can pattern-match on
 * `.status` / `.code`.
 */

import { api } from "./config";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "./storage";

const MOBILE_HEADER = "X-Client-Type";
const MOBILE_VALUE = "mobile";

export class StrixApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string | null,
    public readonly detail: string | null = null,
  ) {
    super(message);
    this.name = "StrixApiError";
  }
}

type FetchOpts = Omit<RequestInit, "body"> & {
  body?: unknown;
  skipAuth?: boolean;
  signal?: AbortSignal;
};

// ---- single-flight refresh -------------------------------------------

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refreshToken = await getRefreshToken();
    if (!refreshToken) return null;
    try {
      const resp = await fetch(api("/auth/refresh"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          [MOBILE_HEADER]: MOBILE_VALUE,
        },
        body: JSON.stringify({ refreshToken }),
      });
      if (!resp.ok) return null;
      const data = (await resp.json()) as {
        accessToken: string;
        refreshToken?: string | null;
      };
      await setTokens({
        accessToken: data.accessToken,
        refreshToken: data.refreshToken ?? refreshToken,
      });
      return data.accessToken;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

// ---- core fetch -------------------------------------------------------

async function doFetch(
  path: string,
  token: string | null,
  opts: FetchOpts,
): Promise<Response> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    [MOBILE_HEADER]: MOBILE_VALUE,
    ...(opts.headers as Record<string, string> | undefined),
  };
  if (opts.body !== undefined && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (token && !opts.skipAuth) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers,
    signal: opts.signal,
  };
  if (opts.body !== undefined) {
    init.body =
      opts.body instanceof FormData
        ? opts.body
        : JSON.stringify(opts.body);
  }
  return fetch(api(path), init);
}

async function throwProblem(resp: Response): Promise<never> {
  let code: string | null = null;
  let detail: string | null = null;
  let title = resp.statusText || "Request failed";
  try {
    const body = (await resp.json()) as {
      title?: string;
      code?: string;
      detail?: string;
    };
    if (body.title) title = body.title;
    if (body.code) code = body.code;
    if (body.detail) detail = body.detail;
  } catch {
    // non-JSON body; fall back to statusText
  }
  throw new StrixApiError(title, resp.status, code, detail);
}

export async function apiFetch<T = unknown>(
  path: string,
  opts: FetchOpts = {},
): Promise<T> {
  let token = await getAccessToken();

  let resp = await doFetch(path, token, opts);

  if (resp.status === 401 && !opts.skipAuth) {
    token = await refreshAccessToken();
    if (token) {
      resp = await doFetch(path, token, opts);
    } else {
      // refresh failed → clear tokens so the auth gate redirects to login
      await clearTokens();
    }
  }

  if (!resp.ok) {
    return throwProblem(resp);
  }

  // 204 no-content — common for DELETE
  if (resp.status === 204) {
    return undefined as T;
  }
  const ct = resp.headers.get("content-type") ?? "";
  if (!ct.includes("json")) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

// Convenience wrappers matching the web client's ergonomics.
export const apiGet = <T>(path: string, opts: FetchOpts = {}) =>
  apiFetch<T>(path, { ...opts, method: "GET" });
export const apiPost = <T>(path: string, body?: unknown, opts: FetchOpts = {}) =>
  apiFetch<T>(path, { ...opts, method: "POST", body });
export const apiPatch = <T>(path: string, body?: unknown, opts: FetchOpts = {}) =>
  apiFetch<T>(path, { ...opts, method: "PATCH", body });
export const apiDelete = <T>(path: string, opts: FetchOpts = {}) =>
  apiFetch<T>(path, { ...opts, method: "DELETE" });
