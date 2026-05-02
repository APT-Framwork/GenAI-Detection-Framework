"use client"

import { cn } from "@/lib/utils"
import { ChevronRight } from "lucide-react"
import { useRouter } from "next/navigation"
import { toast } from "@/lib/toast"

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
  /** When provided, "View Intel" deep-links into Threat Intel filtered
   *  on this host. */
  hostId?: string | null
  className?: string
}

/** Render a real, data-driven narrative for the next-move card. The
 *  previous version hardcoded "aggregate CSV files in /data/export"
 *  copy on every chain — we now describe the actual top prediction. */
function nextMoveNarrative(p: ChainPredictions): string {
  if (!p.predictedNextStageName || p.predictedNextStage == null) {
    return "No forward prediction available — chain is closed or below the confidence threshold."
  }
  const conf = Math.round(p.confidence * 100)
  const stage = p.predictedNextStageName
  const top = p.probabilities
    .slice()
    .sort((a, b) => b.prob - a.prob)
    .slice(0, 3)
    .map((s) => `${s.ckcStageName} ${Math.round(s.prob * 100)}%`)
    .join(" · ")
  if (conf < 25) {
    return `Transformer is uncertain: top hypotheses ${top}. Treat as exploratory.`
  }
  return `Transformer projects the next CKC step is ${stage} (${conf}% confidence). Distribution: ${top}.`
}

export function AIPredictionsPanel({
  predictions,
  hostId,
  className,
}: AIPredictionsPanelProps) {
  const router = useRouter()
  if (!predictions) return null
  const confPct = `${Math.round(predictions.confidence * 100)}%`
  const second = predictions.probabilities
    .filter((p) => p.ckcStage !== predictions.predictedNextStage)
    .sort((a, b) => b.prob - a.prob)[0]
  // Concentration of mass on the top prediction — a fair proxy for
  // "correlation" in the previous static copy. 100% = single-mode
  // distribution, near 0% = uniform / uncertain.
  const top = predictions.probabilities
    .slice()
    .sort((a, b) => b.prob - a.prob)[0]
  const correlationPct = top ? Math.round(top.prob * 100) : 0
  const pred = {
    nextStep: predictions.predictedNextStageName ?? "—",
    aptFamily: `Currently at ${predictions.currentStageName ?? "—"}`,
    analysis: second
      ? `Second-most-likely next stage: ${second.ckcStageName} (${Math.round(second.prob * 100)}%)`
      : "No alternate hypothesis available.",
  }

  return (
    <div className={cn("space-y-6", className)}>
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
          {nextMoveNarrative(predictions)}
        </p>
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-semibold text-[#00343d] dark:text-[var(--strix-text)]">
            Confidence Score:{" "}
            <span className="text-[#00666d] dark:text-[#87edf6]">{confPct}</span>
          </span>
          <button
            onClick={() => {
              if (typeof window === "undefined") return
              const ok = window.confirm(
                `Apply preventive shield against predicted next stage (${pred.nextStep})? The platform will queue an ESCALATE recommendation for operator approval.`,
              )
              if (!ok) return
              toast.warning("Shield queued for approval. (Backend RL counter-measure endpoint not enabled in this build.)", 6000)
            }}
            className="text-[12px] font-semibold text-[#00666d] dark:text-[#87edf6] hover:underline flex items-center gap-0.5"
          >
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
            Top-mass probability:{" "}
            <span className="text-[#00666d] dark:text-[#87edf6]">{correlationPct}%</span>
          </span>
          <button
            onClick={() => {
              // Deep-link into Threat Intel filtered on the host.
              const q = hostId ? `?q=${encodeURIComponent(hostId)}` : ""
              router.push(`/threat-intel${q}`)
            }}
            className="text-[12px] font-semibold text-[#00666d] dark:text-[#87edf6] hover:underline flex items-center gap-0.5"
          >
            View Intel
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
