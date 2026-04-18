/**
 * Mobile auth flows. The backend's §M0 contract:
 *
 *   POST /auth/login   + X-Client-Type: mobile
 *       → { accessToken, expiresIn, tokenType, refreshToken }
 *   POST /auth/refresh + body { refreshToken }
 *       → same shape (rotated refresh token every time)
 *   POST /auth/logout → { ok: true }
 *   GET  /auth/me     → { userId, email, role, isActive }
 *
 * We stash access + refresh in SecureStore and cache `/auth/me` in
 * AsyncStorage-equivalent so the app can show the user identity
 * immediately on cold start while the real /me call validates.
 */

import { apiDelete, apiGet, apiPost, StrixApiError } from "./client";
import {
  clearCachedUser,
  clearTokens,
  getAccessToken,
  setCachedUser,
  setTokens,
} from "./storage";

export type MeResponse = {
  userId: string;
  email: string;
  role: "admin" | "analyst" | "viewer" | string;
  isActive: boolean;
  designation: string | null;
};

type TokenResponse = {
  accessToken: string;
  expiresIn: number;
  tokenType: string;
  refreshToken?: string | null;
};

export async function register(opts: {
  email: string;
  password: string;
  designation?: string;
}): Promise<MeResponse> {
  const token = await apiPost<TokenResponse>(
    "/auth/register",
    {
      email: opts.email,
      password: opts.password,
      designation: opts.designation,
    },
    { skipAuth: true },
  );
  if (!token.refreshToken) {
    throw new StrixApiError(
      "Server did not return a refresh token",
      500,
      "MISSING_REFRESH_TOKEN",
    );
  }
  await setTokens({
    accessToken: token.accessToken,
    refreshToken: token.refreshToken,
  });
  const me = await apiGet<MeResponse>("/auth/me");
  await setCachedUser(me);
  return me;
}


export async function login(opts: {
  email: string;
  password: string;
}): Promise<MeResponse> {
  const token = await apiPost<TokenResponse>(
    "/auth/login",
    { email: opts.email, password: opts.password },
    { skipAuth: true },
  );
  if (!token.refreshToken) {
    // Backend populates refreshToken only when X-Client-Type: mobile
    // is set — the client.ts wrapper always sets it, so this should
    // never happen. Fail loudly if it does.
    throw new StrixApiError(
      "Server did not return a refresh token",
      500,
      "MISSING_REFRESH_TOKEN",
    );
  }
  await setTokens({
    accessToken: token.accessToken,
    refreshToken: token.refreshToken,
  });
  const me = await apiGet<MeResponse>("/auth/me");
  await setCachedUser(me);
  return me;
}

export async function me(): Promise<MeResponse> {
  const user = await apiGet<MeResponse>("/auth/me");
  await setCachedUser(user);
  return user;
}

export async function logout(): Promise<void> {
  // Best-effort server-side logout; regardless, we must wipe local
  // creds so the auth gate redirects to login.
  try {
    await apiPost<{ ok: boolean }>("/auth/logout");
  } catch {
    // ignore — network error shouldn't prevent local logout
  }
  await clearTokens();
  await clearCachedUser();
}

export async function hasTokens(): Promise<boolean> {
  return (await getAccessToken()) !== null;
}

// ---- device registration (M0-B5) --------------------------------------

export type Platform = "ios" | "android" | "web";

export async function registerDevice(opts: {
  expoPushToken: string;
  platform: Platform;
  appVersion?: string;
}): Promise<void> {
  try {
    await apiPost("/auth/devices", opts);
  } catch {
    // non-fatal: push is best-effort
  }
}

export async function unregisterDevice(expoPushToken: string): Promise<void> {
  try {
    await apiDelete(`/auth/devices/${encodeURIComponent(expoPushToken)}`);
  } catch {
    // non-fatal
  }
}
