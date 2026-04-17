import { create } from "zustand";

interface UIState {
  isDark: boolean;
  isLoading: boolean;
  toggleTheme: () => void;
  setLoading: (v: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  isDark: false,
  isLoading: false,
  toggleTheme: () => set((s) => ({ isDark: !s.isDark })),
  setLoading: (v) => set({ isLoading: v }),
}));
