import { create } from "zustand"
import type { UserProfile } from "@/types"

interface AuthState {
  user: UserProfile | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<boolean>
  register: (name: string, email: string, password: string) => Promise<boolean>
  logout: () => void
}

const mockUser: UserProfile = {
  id: "sentinel-core-01",
  name: "SENTINEL_CORE_01",
  designation: "Sentinel-Alpha-B",
  role: "Senior Security Operations Analyst",
  site: "SITE ALPHA",
  level: 4,
  tags: ["INCIDENT_RESPONSE", "THREAT_HUNTING", "CRYPTOGRAPHY"],
  efficiency: 94,
  accuracy: 99.8,
  responseTime: "12m",
  avatar: undefined,
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  login: async (_email: string, _password: string) => {
    // Mock login — always succeeds
    await new Promise((r) => setTimeout(r, 800))
    set({ user: mockUser, isAuthenticated: true })
    return true
  },
  register: async (_name: string, _email: string, _password: string) => {
    await new Promise((r) => setTimeout(r, 800))
    set({ user: mockUser, isAuthenticated: true })
    return true
  },
  logout: () => set({ user: null, isAuthenticated: false }),
}))
