"use client"

// stage-probability-bars.tsx — horizontal bar visualisation of the
// Transformer's per-stage probability distribution for a chain. The
// previous AI Predictions panel showed only the top + second-most-likely
// stages and threw the rest away; this puts the full distribution back
// in the analyst's view.

import type { StageProbability } from "@/lib/api/analysis"
import { cn } from "@/lib/utils"

interface StageProbabilityBarsProps {
  probabilities: StageProbability[]
  predictedNextStage?: number | null
  className?: string
}

function severityCls(stage: number): string {
  if (stage >= 6) return "bg-rose-500"
  if (stage >= 4) return "bg-amber-500"
  if (stage >= 2) return "bg-yellow-500"
  if (stage >= 1) return "bg-cyan-500"
  return "bg-[#497f8b]"
}

export function StageProbabilityBars({
  probabilities,
  predictedNextStage,
  className,
}: StageProbabilityBarsProps) {
  if (probabilities.length === 0) {
    return (
      <div className={cn("text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] italic", className)}>
        No probability distribution available.
      </div>
    )
  }
  const sorted = [...probabilities].sort((a, b) => a.ckcStage - b.ckcStage)
  const max = Math.max(...sorted.map((p) => p.prob), 0.01)

  return (
    <div className={cn("space-y-1.5", className)}>
      {sorted.map((p) => {
        const pct = (p.prob / max) * 100
        const isTop = predictedNextStage != null && p.ckcStage === predictedNextStage
        return (
          <div key={p.ckcStage} className="flex items-center gap-2 text-[11px]">
            <span className="w-[88px] shrink-0 text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] truncate">
              {p.ckcStageName}
            </span>
            <div className="flex-1 h-2.5 rounded-full bg-[rgba(128,182,195,0.18)] dark:bg-[var(--strix-bg-surface)] overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-300",
                  severityCls(p.ckcStage),
                  isTop && "shadow-[0_0_0_1px_rgba(0,242,255,0.5)]",
                )}
                style={{ width: `${Math.max(2, pct)}%` }}
              />
            </div>
            <span
              className={cn(
                "w-[42px] text-right tabular-nums text-[11px] font-semibold",
                isTop
                  ? "text-strix-primary dark:text-strix-cyan"
                  : "text-[#00343d] dark:text-[var(--strix-text)]",
              )}
            >
              {(p.prob * 100).toFixed(1)}%
            </span>
          </div>
        )
      })}
    </div>
  )
}
