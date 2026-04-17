import { create } from "zustand"
import type { Alert, Notification, Severity } from "@/types"

interface AlertState {
  alerts: Alert[]
  notifications: Notification[]
  filter: Severity | "all"
  unreadCount: number
  setFilter: (filter: Severity | "all") => void
  acknowledgeAlert: (id: string) => void
  markNotificationRead: (id: string) => void
  markAllRead: () => void
  addAlert: (alert: Alert) => void
}

export const useAlertStore = create<AlertState>((set) => ({
  alerts: [],
  notifications: [],
  filter: "all",
  unreadCount: 0,
  setFilter: (filter) => set({ filter }),
  acknowledgeAlert: (id) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.id === id ? { ...a, status: "acknowledged" as const } : a
      ),
    })),
  markNotificationRead: (id) =>
    set((state) => ({
      notifications: state.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      ),
      unreadCount: state.notifications.filter((n) => !n.read && n.id !== id).length,
    })),
  markAllRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),
  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts],
    })),
}))
