// -----------------------------------------------------------------------------
// useAuth — login / logout / me hook backed by the /auth endpoints.
//
// The middleware in api/middleware.py guards everything else; this hook is
// the only piece of frontend code that talks to /auth/* directly. The
// Tanstack Query cache keeps `useMe()` warm and invalidates on login/logout.
// -----------------------------------------------------------------------------

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, StrixApiError } from "./client";

export interface MeResponse {
  userId: string;
  email: string;
  role: "admin" | "analyst";
  isActive: boolean;
}

export function useMe() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiFetch<MeResponse>("/auth/me"),
    retry: (failureCount, err) => {
      // 401 means not logged in — don't retry; UI should redirect.
      if (err instanceof StrixApiError && err.status === 401) return false;
      return failureCount < 2;
    },
    staleTime: 60_000,
  });
}

export interface LoginRequest { email: string; password: string; }
export interface TokenResponse { accessToken: string; expiresIn: number; tokenType: string; }

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: LoginRequest) =>
      apiFetch<TokenResponse>("/auth/login", { method: "POST", body: req }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}

export interface RegisterRequest {
  email: string;
  password: string;
  designation?: string;
}

export function useRegister() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: RegisterRequest) =>
      apiFetch<TokenResponse>("/auth/register", { method: "POST", body: req }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: boolean }>("/auth/logout", { method: "POST" }),
    onSettled: () => {
      qc.removeQueries({ queryKey: ["auth", "me"] });
    },
  });
}

/** Convenience: hide UI when role isn't allowed. */
export function useHasRole(...roles: Array<"admin" | "analyst">): boolean {
  const me = useMe();
  if (me.data == null) return false;
  return roles.includes(me.data.role);
}
