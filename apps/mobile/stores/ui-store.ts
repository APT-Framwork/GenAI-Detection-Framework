import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";

/**
 * Non-secret UI preferences. We persist through AsyncStorage (not
 * SecureStore) because none of this is sensitive and SecureStore has
 * tighter size limits + higher read cost.
 *
 * Bootstrap order:
 *   1. Store boots with defaults.
 *   2. `hydrate()` is called once from the root layout — it reads
 *      AsyncStorage and patches the store. Races are impossible since
 *      the `hydrated` flag gates any writeback.
 *   3. `toggleTheme` / `setLoading` etc. mutate synchronously; a
 *      subscription persists the new value to AsyncStorage.
 */

const KEY_PREFS = "strix.prefs.v1";

interface UIState {
  hydrated: boolean;
  isDark: boolean;
  isLoading: boolean;
  /**
   * Count of unacknowledged alerts the user has already "seen" by opening
   * the Alerts tab. The tab-bar badge shows `max(0, unackCount - baseline)`
   * so the number falls to zero on visit but a future incoming alert still
   * surfaces. Session-only — not persisted.
   */
  alertsBadgeBaseline: number;
  toggleTheme: () => void;
  setDark: (v: boolean) => void;
  setLoading: (v: boolean) => void;
  markAlertsSeen: (count: number) => void;
  hydrate: () => Promise<void>;
}

export const useUIStore = create<UIState>((set, get) => ({
  hydrated: false,
  isDark: false,
  isLoading: false,
  alertsBadgeBaseline: 0,

  toggleTheme: () => {
    set((s) => ({ isDark: !s.isDark }));
    void persist(get);
  },
  setDark: (v) => {
    set({ isDark: v });
    void persist(get);
  },
  setLoading: (v) => set({ isLoading: v }),
  markAlertsSeen: (count) => set({ alertsBadgeBaseline: count }),

  hydrate: async () => {
    if (get().hydrated) return;
    try {
      const raw = await AsyncStorage.getItem(KEY_PREFS);
      if (raw) {
        const parsed = JSON.parse(raw) as { isDark?: boolean };
        if (typeof parsed.isDark === "boolean") {
          set({ isDark: parsed.isDark });
        }
      }
    } catch {
      // corrupted or missing — stay with defaults
    } finally {
      set({ hydrated: true });
    }
  },
}));

async function persist(get: () => UIState): Promise<void> {
  const { isDark } = get();
  try {
    await AsyncStorage.setItem(KEY_PREFS, JSON.stringify({ isDark }));
  } catch {
    // best-effort — preferences aren't load-bearing
  }
}
