"use client"

import { cn } from "@/lib/utils"
import { ChevronRight } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useChainAttribution } from "@/lib/api/intel"

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
  /** Required for the Origin Hypothesis card to fetch the chain's CTI
   *  attribution (actor + campaign + confidence). Falls back to the
   *  Transformer-only view when omitted or when the chain has no
   *  attribution. */
  chainId?: string | null
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
  chainId,
  className,
}: AIPredictionsPanelProps) {
  const router = useRouter()
  // Origin Hypothesis is now backed by real CTI attribution data —
  // the Jaccard match the verdicts writer produced when the chain's
  // tactic set crossed the threshold against a known campaign.
  const attribution = useChainAttribution(chainId ?? null)
  if (!predictions) return null
  const confPct = `${Math.round(predictions.confidence * 100)}%`
  const second = predictions.probabilities
    .filter((p) => p.ckcStage !== predictions.predictedNextStage)
    .sort((a, b) => b.prob - a.prob)[0]
  const pred = {
    nextStep: predictions.predictedNextStageName ?? "—",
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
        </div>
      </div>

      {/* Origin Hypothesis — backed by /intel/chains/{id}/attribution.
          When the CTI matcher Jaccard-attributed this chain to a known
          campaign, render the actor + campaign + confidence. Otherwise
          fall back to the runner-up candidates so the analyst still
          sees "we considered these actors". */}
      <div className="bg-[#e7faff]/60 dark:bg-[var(--strix-bg-surface)] rounded-[32px] p-6 border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
        <span className="inline-block px-3 py-1 rounded-[9999px] text-[9px] font-bold uppercase tracking-widest bg-[#87edf6]/20 dark:bg-[#87edf6]/10 text-[#00666d] dark:text-[#87edf6] mb-3">
          Origin Hypothesis
        </span>
        {attribution.data?.attributed && attribution.data.actorName ? (
          <>
            <h4 className="text-lg font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)] mb-1 flex items-center gap-2">
              {attribution.data.actorName}
              {attribution.data.actorMitreGroupId && (
                <span className="font-mono text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] font-normal">
                  {attribution.data.actorMitreGroupId}
                </span>
              )}
            </h4>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-2 uppercase tracking-wider">
              {attribution.data.actorCountry && (
                <span>{attribution.data.actorCountry}</span>
              )}
              {attribution.data.actorMotivation && (
                <span>· {attribution.data.actorMotivation}</span>
              )}
            </div>
            {attribution.data.campaignName && (
              <p className="text-[12px] text-[#00343d] dark:text-[var(--strix-text)] mb-2">
                Matches campaign{" "}
                <Link
                  href={`/intel/campaigns/${attribution.data.campaignId}`}
                  className="text-[#00666d] dark:text-[#87edf6] hover:underline font-semibold"
                >
                  {attribution.data.campaignName}
                </Link>
              </p>
            )}
            {attribution.data.candidates.length > 1 && (
              <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-3">
                Runner-ups:{" "}
                {attribution.data.candidates
                  .filter((c) => c.campaignId !== attribution.data?.campaignId)
                  .slice(0, 2)
                  .map((c) => `${c.actorName ?? "?"} ${c.confidence}%`)
                  .join(" · ")}
              </p>
            )}
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-semibold text-[#00343d] dark:text-[var(--strix-text)]">
                Attribution confidence:{" "}
                <span className="text-[#00666d] dark:text-[#87edf6]">
                  {attribution.data.confidence != null
                    ? `${attribution.data.confidence}%`
                    : "—"}
                </span>
              </span>
              <Link
                href={`/intel/actors/${attribution.data.actorId}`}
                className="text-[12px] font-semibold text-[#00666d] dark:text-[#87edf6] hover:underline flex items-center gap-0.5"
              >
                View Actor
                <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </>
        ) : attribution.data && attribution.data.candidates.length > 0 ? (
          <>
            <h4 className="text-lg font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)] mb-2">
              No attribution above threshold
            </h4>
            <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] leading-relaxed mb-3">
              Tactic set partially matches{" "}
              {attribution.data.candidates
                .slice(0, 3)
                .map((c) => `${c.actorName ?? c.campaignName} (${c.confidence}%)`)
                .join(", ")}
              . None crossed the Jaccard threshold for confident attribution.
            </p>
            <div className="flex items-center justify-end">
              <button
                onClick={() => {
                  const q = hostId ? `?q=${encodeURIComponent(hostId)}` : ""
                  router.push(`/threat-intel${q}`)
                }}
                className="text-[12px] font-semibold text-[#00666d] dark:text-[#87edf6] hover:underline flex items-center gap-0.5"
              >
                View Intel
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </>
        ) : (
          <>
            <h4 className="text-lg font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)] mb-2">
              Unattributed
            </h4>
            <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] leading-relaxed">
              Chain has no MITRE-tagged tactics yet or doesn't match any tracked campaign.
              Attribution runs automatically as more telemetry accumulates.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
