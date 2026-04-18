/**
 * Auth + user state.
 *
 * `status` is the single source of truth for the auth gate:
 *   "booting"   app just opened; we're checking SecureStore for tokens
 *   "anon"      no valid session; /auth/me failed
 *   "authed"    /auth/me returned OK and `user` is populated
 *
 * The store is hydrated once at app start by `bootstrapAuth()` in the
 * root layout. After that, `login()` and `logout()` mutate the store
 * directly so the UI reacts immediately.
 */

import { create } from "zustand";

import {
  login as apiLogin,
  logout as apiLogout,
  me as apiMe,
  register as apiRegister,
  type MeResponse,
} from "../lib/api/auth";
import {
  clearCachedUser,
  getAccessToken,
  getCachedUser,
} from "../lib/api/storage";

type Status = "booting" | "anon" | "authed";

interface UserState {
  status: Status;
  user: MeResponse | null;
  isOnboarded: boolean;
  setOnboarded: (v: boolean) => void;

  /** Called once from the root layout on app start. */
  bootstrap: () => Promise<void>;
  /** Resolves with the fetched `MeResponse`; throws on bad credentials. */
  login: (email: string, password: string) => Promise<MeResponse>;
  /** Register a new analyst; stores tokens + hydrates `user` on success. */
  register: (
    email: string,
    password: string,
    designation?: string,
  ) => Promise<MeResponse>;
  /** Fire-and-forget; always clears local state. */
  logout: () => Promise<void>;
}

export const useUserStore = create<UserState>((set, get) => ({
  status: "booting",
  user: null,
  isOnboarded: false,

  setOnboarded: (v) => set({ isOnboarded: v }),

  bootstrap: async () => {
    // Only bootstrap once; subsequent calls are no-ops.
    if (get().status !== "booting") return;

    const token = await getAccessToken();
    if (!token) {
      set({ status: "anon", user: null });
      return;
    }

    // Show cached user immediately so profile/header render w/o flash.
    const cached = (await getCachedUser()) as MeResponse | null;
    if (cached) {
      set({ status: "authed", user: cached });
    }

    // Validate in the background. On failure (401, network, etc.) fall
    // back to anon — the client already cleared tokens on 401.
    try {
      const user = await apiMe();
      set({ status: "authed", user });
    } catch {
      await clearCachedUser();
      set({ status: "anon", user: null });
    }
  },

  login: async (email, password) => {
    const user = await apiLogin({ email, password });
    set({ status: "authed", user });
    return user;
  },

  register: async (email, password, designation) => {
    const user = await apiRegister({ email, password, designation });
    set({ status: "authed", user });
    return user;
  },

  logout: async () => {
    await apiLogout();
    set({ status: "anon", user: null });
  },
}));
