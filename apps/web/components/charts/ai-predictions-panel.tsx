"use client"

import { cn } from "@/lib/utils"
import { ChevronRight } from "lucide-react"

// Real shape from /api/v1/analysis/chains/{id}/predictions
interface ChainPredictions {
  chainId: string
  currentStage: number
  currentStageName: string
  predictedNextStage: number
  predictedNextStageName: string
  confidence: number
  probabilities: { ckcStage: number; ckcStageName: string; prob: number }[]
}

interface AIPredictionsPanelProps {
  predictions: ChainPredictions | null | undefined
  className?: string
}

export function AIPredictionsPanel({
  predictions,
  className,
}: AIPredictionsPanelProps) {
  if (!predictions) return null
  const confPct = `${Math.round(predictions.confidence * 100)}%`
  const second = predictions.probabilities
    .filter((p) => p.ckcStage !== predictions.predictedNextStage)
    .sort((a, b) => b.prob - a.prob)[0]
  const pred = {
    nextStep: predictions.predictedNextStageName,
    aptFamily: `Currently at ${predictions.currentStageName}`,
    analysis: second
      ? `Second-most-likely next stage: ${second.ckcStageName} (${Math.round(second.prob * 100)}%)`
      : "No alternate hypothesis available.",
  }

  return (
    <div className={cn("space-y-6", className)}>
      {/* Title */}
      <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
        AI Predictions
      </h3>

      {/* Next Expected Move */}
      <div className="bg-[#e7faff]/60 dark:bg-[var(--strix-bg-surface)] rounded-[32px] p-6 border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
        <span className="inline-block px-3 py-1 rounded-[9999px] text-[9px] font-bold uppercase tracking-widest bg-[#87edf6]/20 dark:bg-[#87edf6]/10 text-[#00666d] dark:text-[#87edf6] mb-3">
          Next Expected Move
        </span>
        <h4 className="text-lg font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)] mb-2">
          {pred.nextStep}
        </h4>
        <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] leading-relaxed mb-4">
          System predicts attacker will attempt to aggregate CSV files in the
          /data/export folder within the next 6 minutes.
        </p>
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-semibold text-[#00343d] dark:text-[var(--strix-text)]">
            Confidence Score:{" "}
            <span className="text-[#00666d] dark:text-[#87edf6]">{confPct}</span>
          </span>
          <button className="text-[12px] font-semibold text-[#00666d] dark:text-[#87edf6] hover:underline flex items-center gap-0.5">
            Apply Shield
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Origin Hypothesis */}
      <div className="bg-[#e7faff]/60 dark:bg-[var(--strix-bg-surface)] rounded-[32px] p-6 border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
        <span className="inline-block px-3 py-1 rounded-[9999px] text-[9px] font-bold uppercase tracking-widest bg-[#87edf6]/20 dark:bg-[#87edf6]/10 text-[#00666d] dark:text-[#87edf6] mb-3">
          Origin Hypothesis
        </span>
        <h4 className="text-lg font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)] mb-2">
          {pred.aptFamily}
        </h4>
        <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] leading-relaxed mb-4">
          {pred.analysis}
        </p>
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-semibold text-[#00343d] dark:text-[var(--strix-text)]">
            Correlation:{" "}
            <span className="text-[#00666d] dark:text-[#87edf6]">82%</span>
          </span>
          <button className="text-[12px] font-semibold text-[#00666d] dark:text-[#87edf6] hover:underline flex items-center gap-0.5">
            View Intel
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
