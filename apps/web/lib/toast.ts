// Tiny toast store. No external lib — zustand only. The Toaster
// component (apps/web/components/layout/toaster.tsx) subscribes to
// this store and renders the stack. Call `toast(...)` from anywhere.

import { create } from "zustand";

export type ToastKind = "info" | "success" | "warning" | "error";

export interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
  /** ms; default 3500. */
  ttl: number;
}

interface ToastState {
  items: ToastItem[];
  push: (msg: string, kind?: ToastKind, ttl?: number) => number;
  dismiss: (id: number) => void;
}

let _seq = 1;

export const useToastStore = create<ToastState>((set) => ({
  items: [],
  push: (message, kind = "info", ttl = 3500) => {
    const id = _seq++;
    set((s) => ({ items: [...s.items, { id, message, kind, ttl }] }));
    if (ttl > 0) {
      setTimeout(() => {
        set((s) => ({ items: s.items.filter((t) => t.id !== id) }));
      }, ttl);
    }
    return id;
  },
  dismiss: (id) =>
    set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}));

/** Convenience helpers. */
export const toast = {
  info: (msg: string, ttl?: number) => useToastStore.getState().push(msg, "info", ttl),
  success: (msg: string, ttl?: number) => useToastStore.getState().push(msg, "success", ttl),
  warning: (msg: string, ttl?: number) => useToastStore.getState().push(msg, "warning", ttl),
  error: (msg: string, ttl?: number) => useToastStore.getState().push(msg, "error", ttl),
};
