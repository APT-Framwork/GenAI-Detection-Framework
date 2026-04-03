import { create } from "zustand";
import { Alert, mockAlerts, Severity } from "../lib/mock-data";

interface AlertsState {
  alerts: Alert[];
  filter: Severity | "all";
  unreadCount: number;
  setFilter: (filter: Severity | "all") => void;
  acknowledge: (id: string) => void;
  addAlert: (alert: Alert) => void;
  filteredAlerts: () => Alert[];
}

export const useAlertsStore = create<AlertsState>((set, get) => ({
  alerts: mockAlerts,
  filter: "all",
  unreadCount: mockAlerts.filter((a) => !a.acknowledged).length,

  setFilter: (filter) => set({ filter }),

  acknowledge: (id) =>
    set((state) => {
      const alerts = state.alerts.map((a) =>
        a.id === id ? { ...a, acknowledged: true } : a
      );
      return {
        alerts,
        unreadCount: alerts.filter((a) => !a.acknowledged).length,
      };
    }),

  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts],
      unreadCount: state.unreadCount + (alert.acknowledged ? 0 : 1),
    })),

  filteredAlerts: () => {
    const { alerts, filter } = get();
    if (filter === "all") return alerts;
    return alerts.filter((a) => a.severity === filter);
  },
}));
