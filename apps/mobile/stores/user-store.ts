import { create } from "zustand";
import { mockUser, User } from "../lib/mock-data";

interface UserState {
  user: User;
  isOnboarded: boolean;
  setOnboarded: (v: boolean) => void;
}

export const useUserStore = create<UserState>((set) => ({
  user: mockUser,
  isOnboarded: false,
  setOnboarded: (v) => set({ isOnboarded: v }),
}));
