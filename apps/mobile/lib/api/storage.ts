/**
 * Token storage on SecureStore (encrypted keychain on iOS,
 * EncryptedSharedPreferences on Android). Web falls back to
 * localStorage because SecureStore is a no-op on `expo-web` builds.
 *
 * Keys:
 *   strix.access   — short-lived JWT (15 min)
 *   strix.refresh  — long-lived JWT (7 days)
 *   strix.user     — cached /auth/me payload (plain JSON, not a secret)
 */

import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const KEY_ACCESS = "strix.access";
const KEY_REFRESH = "strix.refresh";
const KEY_USER = "strix.user";

async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") {
    globalThis.localStorage?.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function getItem(key: string): Promise<string | null> {
  if (Platform.OS === "web") {
    return globalThis.localStorage?.getItem(key) ?? null;
  }
  return await SecureStore.getItemAsync(key);
}

async function deleteItem(key: string): Promise<void> {
  if (Platform.OS === "web") {
    globalThis.localStorage?.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

export async function getAccessToken(): Promise<string | null> {
  return getItem(KEY_ACCESS);
}

export async function getRefreshToken(): Promise<string | null> {
  return getItem(KEY_REFRESH);
}

export async function setTokens(opts: {
  accessToken: string;
  refreshToken?: string | null;
}): Promise<void> {
  await setItem(KEY_ACCESS, opts.accessToken);
  if (opts.refreshToken) {
    await setItem(KEY_REFRESH, opts.refreshToken);
  }
}

export async function clearTokens(): Promise<void> {
  await Promise.all([deleteItem(KEY_ACCESS), deleteItem(KEY_REFRESH)]);
}

export async function getCachedUser(): Promise<unknown | null> {
  const raw = await getItem(KEY_USER);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function setCachedUser(user: unknown): Promise<void> {
  await setItem(KEY_USER, JSON.stringify(user));
}

export async function clearCachedUser(): Promise<void> {
  await deleteItem(KEY_USER);
}
