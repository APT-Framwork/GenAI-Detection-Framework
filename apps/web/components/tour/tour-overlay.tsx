"use client"

// -----------------------------------------------------------------------------
// Guided-tour overlay — spotlight + tooltip renderer.
//
// Mounted once in the dashboard layout. When the tour is active it:
//   1. navigates to the step's route if needed,
//   2. polls for the step's [data-tour] target (pages hydrate + fetch),
//   3. scrolls it into view and draws a spotlight cutout over it,
//   4. positions the explainer card on the preferred side, flipping when it
//      doesn't fit, and
//   5. re-measures on scroll / resize / layout shift (live SSE data moves
//      things around).
//
// Steps with target: null render as a centered modal (welcome / finish).
// Also owns the first-login auto-start (localStorage-gated, desktop only).
// -----------------------------------------------------------------------------

import { useCallback, useEffect, useRef, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { X, ArrowLeft, ArrowRight, Lightbulb, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"
import { TOUR_STEPS, type TourStep } from "@/lib/tour-steps"
import { isTourDone, useTourStore } from "@/stores/tour-store"

const CARD_W = 380 // px — fixed card width, height measured after render
const GAP = 14 // px — spotlight ↔ card gap
const EDGE = 12 // px — min distance from viewport edges
const SPOT_PAD = 8 // px — spotlight padding around the target rect

type Box = { top: number; left: number; width: number; height: number }

function measure(el: Element): Box {
  const r = el.getBoundingClientRect()
  return { top: r.top, left: r.left, width: r.width, height: r.height }
}

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)

/** Pick a card position around the spotlight box, flipping until it fits. */
function placeCard(
  spot: Box,
  cardH: number,
  preferred: TourStep["placement"],
): { top: number; left: number } {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const centerLeft = clamp(spot.left + spot.width / 2 - CARD_W / 2, EDGE, vw - CARD_W - EDGE)
  const centerTop = clamp(spot.top + spot.height / 2 - cardH / 2, EDGE, vh - cardH - EDGE)

  const fits = {
    bottom: spot.top + spot.height + GAP + cardH <= vh - EDGE,
    top: spot.top - GAP - cardH >= EDGE,
    right: spot.left + spot.width + GAP + CARD_W <= vw - EDGE,
    left: spot.left - GAP - CARD_W >= EDGE,
  }
  const pos = {
    bottom: () => ({ top: spot.top + spot.height + GAP, left: centerLeft }),
    top: () => ({ top: spot.top - GAP - cardH, left: centerLeft }),
    right: () => ({ top: centerTop, left: spot.left + spot.width + GAP }),
    left: () => ({ top: centerTop, left: spot.left - GAP - CARD_W }),
  }

  const order: Array<keyof typeof fits> =
    preferred && preferred !== "auto"
      ? [preferred, "bottom", "top", "right", "left"]
      : ["bottom", "top", "right", "left"]
  for (const side of order) if (fits[side]) return pos[side]()

  // Nothing fits (huge target) — pin the card to the lower part of the screen.
  return { top: vh - cardH - 24, left: clamp(vw / 2 - CARD_W / 2, EDGE, vw - CARD_W - EDGE) }
}

export function TourOverlay() {
  const { active, stepIndex, start, stop, next, prev } = useTourStore()
  const pathname = usePathname()
  const router = useRouter()

  const step: TourStep | undefined = TOUR_STEPS[stepIndex]
  const [spot, setSpot] = useState<Box | null>(null) // null → modal or searching
  const [searching, setSearching] = useState(false)
  const cardRef = useRef<HTMLDivElement>(null)
  const [cardPos, setCardPos] = useState<{ top: number; left: number } | null>(null)

  // ---- first-login auto-start (desktop only, once ever per browser) --------
  useEffect(() => {
    if (isTourDone()) return
    if (window.innerWidth < 1024) return
    if (pathname !== "/") return
    const t = setTimeout(() => {
      // Re-check: the operator may have started it manually meanwhile.
      if (!useTourStore.getState().active && !isTourDone()) start(0)
    }, 900)
    return () => clearTimeout(t)
    // Mount-only on purpose: auto-start fires for the first dashboard visit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- route sync ----------------------------------------------------------
  useEffect(() => {
    if (!active || !step) return
    if (step.route !== pathname) router.push(step.route)
  }, [active, step, pathname, router])

  // ---- find + track the target --------------------------------------------
  useEffect(() => {
    if (!active || !step) return
    setSpot(null)
    setCardPos(null)
    if (!step.target) return // modal step

    if (step.route !== pathname) return // wait for navigation
    setSearching(true)
    let cancelled = false
    let tracker: number | undefined
    const deadline = Date.now() + 5000

    const track = (el: Element) => {
      const update = () => {
        if (cancelled) return
        setSpot(measure(el))
      }
      update()
      // Live pages shift (SSE data, charts hydrating) — cheap re-measure loop
      // plus scroll/resize listeners keeps the spotlight glued to its target.
      tracker = window.setInterval(update, 250)
      window.addEventListener("scroll", update, true)
      window.addEventListener("resize", update)
      cleanupRef.current = () => {
        if (tracker) window.clearInterval(tracker)
        window.removeEventListener("scroll", update, true)
        window.removeEventListener("resize", update)
      }
    }

    const poll = () => {
      if (cancelled) return
      const el = document.querySelector(step.target as string)
      if (el) {
        setSearching(false)
        el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" })
        // Let the smooth scroll settle before first measure.
        setTimeout(() => !cancelled && track(el), 350)
      } else if (Date.now() < deadline) {
        setTimeout(poll, 120)
      } else {
        // Target never appeared (empty state, hidden panel) — degrade to a
        // centered card so the explanation still lands.
        setSearching(false)
        setSpot(null)
      }
    }
    const cleanupRef = { current: () => {} }
    poll()
    return () => {
      cancelled = true
      cleanupRef.current()
    }
  }, [active, step, pathname])

  // ---- card placement (needs rendered card height) -------------------------
  useEffect(() => {
    if (!active || !step) return
    const el = cardRef.current
    if (!el) return
    const h = el.offsetHeight
    if (step.target && spot) {
      setCardPos(placeCard(spot, h, step.placement))
    } else {
      setCardPos({
        top: clamp(window.innerHeight / 2 - h / 2, EDGE, window.innerHeight - h - EDGE),
        left: clamp(window.innerWidth / 2 - CARD_W / 2, EDGE, window.innerWidth - CARD_W - EDGE),
      })
    }
  }, [active, step, spot, stepIndex])

  // ---- keyboard ------------------------------------------------------------
  const onKey = useCallback(
    (e: KeyboardEvent) => {
      if (!useTourStore.getState().active) return
      if (e.key === "Escape") stop(false)
      else if (e.key === "ArrowRight" || e.key === "Enter") next()
      else if (e.key === "ArrowLeft") prev()
      else return
      e.preventDefault()
      e.stopPropagation()
    },
    [stop, next, prev],
  )
  useEffect(() => {
    if (!active) return
    window.addEventListener("keydown", onKey, true)
    return () => window.removeEventListener("keydown", onKey, true)
  }, [active, onKey])

  if (!active || !step) return null

  const isModal = !step.target || (!spot && !searching)
  const pct = Math.round(((stepIndex + 1) / TOUR_STEPS.length) * 100)

  return (
    <div className="fixed inset-0 z-[9999]" role="dialog" aria-modal="true" aria-label="Platform tutorial">
      {/* Backdrop. Modal steps dim everything; spotlight steps punch a hole
          via the box-shadow trick on the cutout div below. */}
      {isModal || !spot ? (
        <div className="absolute inset-0 bg-[#020a14]/70 backdrop-blur-[1.5px] transition-opacity duration-300" />
      ) : (
        <div
          className="absolute rounded-xl border-2 border-strix-cyan/80 transition-all duration-300 ease-out pointer-events-none"
          style={{
            top: spot.top - SPOT_PAD,
            left: spot.left - SPOT_PAD,
            width: spot.width + SPOT_PAD * 2,
            height: spot.height + SPOT_PAD * 2,
            boxShadow: "0 0 0 200vmax rgba(2, 10, 20, 0.72), 0 0 24px rgba(0, 242, 255, 0.35)",
          }}
        />
      )}

      {/* Explainer card */}
      <div
        ref={cardRef}
        className={cn(
          "absolute rounded-2xl border border-[var(--strix-border)] bg-[var(--strix-bg-card)] shadow-2xl",
          "transition-all duration-300 ease-out",
          cardPos ? "opacity-100" : "opacity-0",
        )}
        style={{ width: CARD_W, top: cardPos?.top ?? 0, left: cardPos?.left ?? 0 }}
      >
        {/* Progress bar */}
        <div className="h-1 rounded-t-2xl bg-[var(--strix-bg-surface)] overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-strix-primary to-strix-cyan transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="p-5">
          {/* Header row */}
          <div className="flex items-center justify-between mb-2">
            <span className="inline-flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-[1.2px] text-strix-primary dark:text-strix-cyan">
              <Sparkles className="h-3 w-3" />
              {step.section}
              <span className="text-[var(--strix-text-muted)] font-medium tracking-normal normal-case">
                · step {stepIndex + 1} of {TOUR_STEPS.length}
              </span>
            </span>
            <button
              onClick={() => stop(false)}
              aria-label="Exit tutorial"
              className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)] transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <h3 className="text-[16px] font-bold text-[var(--strix-text)] tracking-tight mb-1.5 font-[family-name:var(--font-space-grotesk)]">
            {step.title}
          </h3>
          <p className="text-[12px] leading-relaxed text-[var(--strix-text-muted)]">{step.body}</p>

          {step.tip && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/25 bg-amber-500/8 px-3 py-2">
              <Lightbulb className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-amber-500" />
              <p className="text-[11px] leading-relaxed text-[var(--strix-text-muted)]">{step.tip}</p>
            </div>
          )}

          {/* Controls */}
          <div className="mt-4 flex items-center justify-between">
            <button
              onClick={() => stop(false)}
              className="text-[10px] uppercase tracking-wider text-[var(--strix-text-muted)] hover:text-[var(--strix-text)] transition-colors"
            >
              Skip tour
            </button>
            <div className="flex items-center gap-2">
              <button
                onClick={prev}
                disabled={stepIndex === 0}
                className={cn(
                  "flex items-center gap-1 rounded-lg border border-[var(--strix-border)] px-3 py-1.5 text-[11px] font-semibold transition-colors",
                  stepIndex === 0
                    ? "opacity-40 cursor-not-allowed text-[var(--strix-text-muted)]"
                    : "text-[var(--strix-text)] hover:bg-[var(--strix-bg-surface)]",
                )}
              >
                <ArrowLeft className="h-3 w-3" />
                Back
              </button>
              <button
                onClick={next}
                className="flex items-center gap-1 rounded-lg bg-strix-primary dark:bg-strix-cyan px-4 py-1.5 text-[11px] font-bold text-white dark:text-[#00343d] hover:opacity-90 transition-opacity"
              >
                {stepIndex === TOUR_STEPS.length - 1 ? "Finish" : "Next"}
                {stepIndex < TOUR_STEPS.length - 1 && <ArrowRight className="h-3 w-3" />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
