// -----------------------------------------------------------------------------
// Guided-tour state. The overlay (components/tour/tour-overlay.tsx) renders
// from this store; launchers (topbar ? icon, Support page, first-login
// auto-start) call start(). Completion / skip is persisted in localStorage so
// the auto-start only ever fires for a fresh operator.
// -----------------------------------------------------------------------------

import { create } from "zustand"
import { TOUR_STEPS } from "@/lib/tour-steps"

export const TOUR_DONE_KEY = "strix:tour:v1"

export function isTourDone(): boolean {
  if (typeof window === "undefined") return true
  try {
    return window.localStorage.getItem(TOUR_DONE_KEY) != null
  } catch {
    return true
  }
}

function markTourDone(how: "completed" | "skipped") {
  try {
    window.localStorage.setItem(TOUR_DONE_KEY, how)
  } catch {
    /* private-mode etc. — non-fatal */
  }
}

interface TourState {
  active: boolean
  stepIndex: number
  start: (fromIndex?: number) => void
  stop: (completed: boolean) => void
  next: () => void
  prev: () => void
}

export const useTourStore = create<TourState>((set, get) => ({
  active: false,
  stepIndex: 0,

  start: (fromIndex = 0) => set({ active: true, stepIndex: fromIndex }),

  stop: (completed) => {
    markTourDone(completed ? "completed" : "skipped")
    set({ active: false, stepIndex: 0 })
  },

  next: () => {
    const { stepIndex } = get()
    if (stepIndex >= TOUR_STEPS.length - 1) {
      get().stop(true)
      return
    }
    set({ stepIndex: stepIndex + 1 })
  },

  prev: () => {
    const { stepIndex } = get()
    if (stepIndex > 0) set({ stepIndex: stepIndex - 1 })
  },
}))
