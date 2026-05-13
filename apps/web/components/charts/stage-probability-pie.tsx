"use client"

// stage-probability-pie.tsx — donut chart showing the Transformer's
// per-stage CKC probability distribution for a chain. Each slice is a
// distinct CKC stage, click/hover selects it and pops a label with the
// stage name + percentage in the center of the donut. The slice for the
// model's argmax (`predictedNextStage`) is selected by default so the
// chart always has a meaningful initial reading.
//
// Data comes from /api/v1/analysis/chains/{id}/predictions — the worker
// persists the full softmax in `detections.transformer_probabilities`
// (migration 0016); rows written before then surface as the legacy
// reconstructed distribution. This component never invents data.

import type { StageProbability } from "@/lib/api/analysis"
import { cn } from "@/lib/utils"
import { useMemo, useState } from "react"

interface StageProbabilityPieProps {
  probabilities: StageProbability[]
  predictedNextStage?: number | null
  className?: string
  /** Outer SVG diameter in px. The donut hole is fixed at 55% of this. */
  size?: number
}

// CKC stage → colour. Chosen so neighbouring stages remain distinguishable
// even on a small chart and so the colour family communicates severity
// (cool → warm → red as the kill chain progresses).
const STAGE_COLOURS: Record<number, string> = {
  0: "#34D399", // BENIGN — emerald
  1: "#22D3EE", // RECONNAISSANCE — cyan
  2: "#60A5FA", // WEAPONIZATION — blue
  3: "#A78BFA", // DELIVERY — violet
  4: "#F59E0B", // EXPLOITATION — amber
  5: "#FB923C", // INSTALLATION — orange
  6: "#F43F5E", // COMMAND_AND_CONTROL — rose
  7: "#DC2626", // ACTIONS_ON_OBJECTIVES — red
}

const STAGE_FALLBACK = "#7C8FA1"

const TAU = Math.PI * 2

interface PreparedSlice {
  stage: number
  name: string
  prob: number
  pct: number          // 0..100
  startAngle: number   // radians from -π/2 (top)
  endAngle: number
  color: string
}

export function StageProbabilityPie({
  probabilities,
  predictedNextStage,
  className,
  size = 220,
}: StageProbabilityPieProps) {
  const total = probabilities.reduce((s, p) => s + Math.max(0, p.prob), 0)

  const slices: PreparedSlice[] = useMemo(() => {
    if (total <= 0) return []
    const sorted = [...probabilities].sort((a, b) => a.ckcStage - b.ckcStage)
    let cursor = -Math.PI / 2 // start at 12 o'clock
    const out: PreparedSlice[] = []
    for (const p of sorted) {
      const frac = Math.max(0, p.prob) / total
      const sweep = frac * TAU
      out.push({
        stage: p.ckcStage,
        name: p.ckcStageName,
        prob: p.prob,
        pct: frac * 100,
        startAngle: cursor,
        endAngle: cursor + sweep,
        color: STAGE_COLOURS[p.ckcStage] ?? STAGE_FALLBACK,
      })
      cursor += sweep
    }
    return out
  }, [probabilities, total])

  // Default selection: the predicted argmax if it's present in the
  // distribution; otherwise the largest slice. We re-evaluate when the
  // upstream probabilities change so a live update can refocus the chart.
  const [selected, setSelected] = useState<number | null>(null)
  const effectiveSelected = useMemo<number | null>(() => {
    if (slices.length === 0) return null
    if (selected != null && slices.some((s) => s.stage === selected)) {
      return selected
    }
    if (
      predictedNextStage != null &&
      slices.some((s) => s.stage === predictedNextStage)
    ) {
      return predictedNextStage
    }
    return slices.reduce((m, s) => (s.prob > m.prob ? s : m), slices[0]).stage
  }, [slices, selected, predictedNextStage])

  if (slices.length === 0) {
    return (
      <div
        className={cn(
          "rounded-xl border border-dashed border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] py-6 text-center text-xs text-[#497f8b] dark:text-[var(--strix-text-muted)]",
          className
        )}
      >
        No probability distribution available.
      </div>
    )
  }

  const cx = size / 2
  const cy = size / 2
  const outerR = size / 2 - 4
  const innerR = outerR * 0.55
  const selectedSlice = slices.find((s) => s.stage === effectiveSelected) ?? null

  return (
    <div className={cn("flex flex-col items-center gap-3", className)}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          role="img"
          aria-label="Per-stage CKC probability distribution"
        >
          {slices.map((s) => {
            const isSelected = s.stage === effectiveSelected
            const path = arcPath({
              cx,
              cy,
              innerR,
              outerR: isSelected ? outerR : outerR - 3,
              startAngle: s.startAngle,
              endAngle: s.endAngle,
            })
            return (
              <path
                key={s.stage}
                d={path}
                fill={s.color}
                opacity={effectiveSelected == null || isSelected ? 1 : 0.45}
                stroke="var(--strix-bg-card)"
                strokeWidth={1.5}
                className="cursor-pointer transition-opacity"
                onMouseEnter={() => setSelected(s.stage)}
                onClick={() =>
                  setSelected((prev) => (prev === s.stage ? null : s.stage))
                }
              >
                <title>{`${s.name} — ${s.pct.toFixed(1)}%`}</title>
              </path>
            )
          })}
        </svg>

        {/* Centre readout — stage name + percentage of the active slice */}
        {selectedSlice && (
          <div
            className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center"
            style={{ color: selectedSlice.color }}
          >
            <span className="text-[9px] uppercase tracking-widest opacity-80">
              {selectedSlice.name.replace(/_/g, " ")}
            </span>
            <span className="text-2xl font-bold tabular-nums leading-tight mt-0.5">
              {selectedSlice.pct.toFixed(1)}%
            </span>
            <span className="text-[9px] uppercase tracking-widest text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-1">
              stage {selectedSlice.stage}
            </span>
          </div>
        )}
      </div>

      <PieLegend
        slices={slices}
        selected={effectiveSelected}
        onSelect={(stage) =>
          setSelected((prev) => (prev === stage ? null : stage))
        }
      />
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Legend — click swatches to focus the matching slice
// ────────────────────────────────────────────────────────────────────────────

function PieLegend({
  slices,
  selected,
  onSelect,
}: {
  slices: PreparedSlice[]
  selected: number | null
  onSelect: (stage: number) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-1 w-full">
      {slices.map((s) => {
        const isSelected = s.stage === selected
        return (
          <button
            key={s.stage}
            type="button"
            onClick={() => onSelect(s.stage)}
            onMouseEnter={() => onSelect(s.stage)}
            className={cn(
              "group flex items-center gap-1.5 px-1.5 py-1 rounded transition-colors text-left",
              isSelected
                ? "bg-[var(--strix-bg-surface)]"
                : "hover:bg-[var(--strix-bg-surface)]/60"
            )}
          >
            <span
              className="h-2.5 w-2.5 rounded-[3px] shrink-0"
              style={{
                background: s.color,
                opacity: selected == null || isSelected ? 1 : 0.5,
              }}
            />
            <span
              className={cn(
                "text-[10px] font-mono truncate flex-1",
                isSelected
                  ? "text-[var(--strix-text)]"
                  : "text-[#497f8b] dark:text-[var(--strix-text-muted)]"
              )}
              title={s.name}
            >
              {s.name}
            </span>
            <span
              className={cn(
                "text-[10px] tabular-nums font-semibold",
                isSelected
                  ? "text-[var(--strix-text)]"
                  : "text-[#497f8b] dark:text-[var(--strix-text-muted)]"
              )}
            >
              {s.pct.toFixed(1)}%
            </span>
          </button>
        )
      })}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Donut arc path. Falls back to a closed-ring path when a slice covers the
// entire circle (one stage at 100%), since SVG arcs can't draw a full
// circle with a single A command.
// ────────────────────────────────────────────────────────────────────────────

function arcPath({
  cx,
  cy,
  innerR,
  outerR,
  startAngle,
  endAngle,
}: {
  cx: number
  cy: number
  innerR: number
  outerR: number
  startAngle: number
  endAngle: number
}): string {
  const sweep = endAngle - startAngle
  if (sweep >= TAU - 1e-6) {
    // Full ring — two opposing half-arcs to avoid the single-A degeneracy.
    const x1 = cx + outerR
    const y1 = cy
    const x2 = cx - outerR
    const y2 = cy
    const ix1 = cx + innerR
    const iy1 = cy
    const ix2 = cx - innerR
    const iy2 = cy
    return [
      `M ${x1} ${y1}`,
      `A ${outerR} ${outerR} 0 1 1 ${x2} ${y2}`,
      `A ${outerR} ${outerR} 0 1 1 ${x1} ${y1}`,
      `M ${ix1} ${iy1}`,
      `A ${innerR} ${innerR} 0 1 0 ${ix2} ${iy2}`,
      `A ${innerR} ${innerR} 0 1 0 ${ix1} ${iy1}`,
      "Z",
    ].join(" ")
  }
  const largeArc = sweep > Math.PI ? 1 : 0
  const sx = cx + outerR * Math.cos(startAngle)
  const sy = cy + outerR * Math.sin(startAngle)
  const ex = cx + outerR * Math.cos(endAngle)
  const ey = cy + outerR * Math.sin(endAngle)
  const isx = cx + innerR * Math.cos(endAngle)
  const isy = cy + innerR * Math.sin(endAngle)
  const iex = cx + innerR * Math.cos(startAngle)
  const iey = cy + innerR * Math.sin(startAngle)
  return [
    `M ${sx} ${sy}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 1 ${ex} ${ey}`,
    `L ${isx} ${isy}`,
    `A ${innerR} ${innerR} 0 ${largeArc} 0 ${iex} ${iey}`,
    "Z",
  ].join(" ")
}
