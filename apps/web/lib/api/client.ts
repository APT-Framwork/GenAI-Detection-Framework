// -----------------------------------------------------------------------------
// Typed fetch client.
//
// Cookies (`strix_access`, `strix_refresh`, `strix_csrf`) are sent automatically
// because every request opts into `credentials: "include"`. Mutating requests
// echo `strix_csrf` back into the `X-CSRF-Token` header per the double-submit
// pattern (P4-9).
//
// On a 401 the client tries the refresh endpoint exactly once. If that also
// fails the original error is rethrown — the auth provider downstream catches
// it and pushes the user to /login.
// -----------------------------------------------------------------------------

const API_BASE: string =
  (process.env.NEXT_PUBLIC_STRIX_API_BASE ?? "/api/v1").replace(/\/$/, "");

export class StrixApiError extends Error {
  status: number;
  code?: string;
  problem?: Problem;
  constructor(status: number, problem: Problem | null, message?: string) {
    super(message ?? problem?.title ?? `HTTP ${status}`);
    this.status = status;
    this.code = problem?.code;
    this.problem = problem ?? undefined;
  }
}

/** RFC-7807 Problem+JSON shape returned by the backend. */
export interface Problem {
  type?: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  code?: string;
  extra?: Record<string, unknown>;
}

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
}

interface ApiOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Skip the auto-refresh-on-401 retry (used by the refresh call itself). */
  skipRefresh?: boolean;
}

/**
 * Issue a request to the STRIX API. Throws `StrixApiError` on non-2xx.
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const { body, headers, skipRefresh, ...rest } = options;
  const method = (rest.method ?? "GET").toUpperCase();
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;

  const finalHeaders = new Headers(headers);
  if (body !== undefined && !finalHeaders.has("Content-Type")) {
    finalHeaders.set("Content-Type", "application/json");
  }
  if (MUTATING.has(method)) {
    const csrf = readCookie("strix_csrf");
    if (csrf) finalHeaders.set("X-CSRF-Token", csrf);
  }

  const init: RequestInit = {
    ...rest,
    method,
    credentials: "include",
    headers: finalHeaders,
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
        ? body
        : JSON.stringify(body),
  };

  let resp = await fetch(url, init);

  if (resp.status === 401 && !skipRefresh && !path.startsWith("/auth/")) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      // Re-issue with a fresh CSRF token.
      if (MUTATING.has(method)) {
        const csrf = readCookie("strix_csrf");
        if (csrf) finalHeaders.set("X-CSRF-Token", csrf);
      }
      resp = await fetch(url, { ...init, headers: finalHeaders });
    }
  }

  if (resp.status === 204 || resp.status === 205) {
    return undefined as T;
  }
  const text = await resp.text();
  const json: unknown = text.length ? safeJson(text) : null;

  if (!resp.ok) {
    const problem =
      json && typeof json === "object" && "title" in (json as object)
        ? (json as Problem)
        : null;
    throw new StrixApiError(resp.status, problem);
  }
  return json as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

let refreshInFlight: Promise<boolean> | null = null;
async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const resp = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        return resp.ok;
      } catch {
        return false;
      } finally {
        // Allow retries on the next 401.
        setTimeout(() => {
          refreshInFlight = null;
        }, 0);
      }
    })();
  }
  return refreshInFlight;
}
