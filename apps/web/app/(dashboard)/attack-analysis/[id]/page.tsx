"use client"

import { useEffect, useMemo } from "react"
import { useRouter } from "next/navigation"

import { AIPredictionsPanel } from "@/components/charts/ai-predictions-panel"
import { KillChainProgression } from "@/components/charts/kill-chain-progression"
import { ChainStageTimeline } from "@/components/charts/chain-stage-timeline"
import { AffectedHostsTable } from "@/components/charts/affected-hosts-table"
import { StageProbabilityBars } from "@/components/charts/stage-probability-bars"
import { OperatorNotes } from "@/components/charts/operator-notes"
import {
  useChainDwellTime,
  useChainInfection,
  useChainList,
  useChainPredictions,
  useCkcProgression,
} from "@/lib/api/analysis"
import type { CkcProgressionStep } from "@/lib/api/analysis"
import type { KillChainStage } from "@/types"
import { downloadJson } from "@/lib/download"
import { toast } from "@/lib/toast"
import {
  Clock,
  FileText,
  Loader2,
  Target,
  Users,
  Zap,
} from "lucide-react"

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—"
  if (seconds === 0) return "<1s"
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`
  if (m > 0) return `${m}m ${String(s).padStart(2, "0")}s`
  return `${s}s`
}

function severityFromCkc(stage: number): { label: string; cls: string } {
  if (stage >= 6) return { label: "Critical", cls: "bg-red-500/10 text-red-500 border-red-500/20" }
  if (stage >= 4) return { label: "High", cls: "bg-orange-500/10 text-orange-500 border-orange-500/20" }
  if (stage >= 2) return { label: "Medium", cls: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20" }
  if (stage >= 1) return { label: "Low", cls: "bg-cyan-500/10 text-cyan-600 border-cyan-500/20" }
  return { label: "Benign", cls: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" }
}

/** Adapt the API's CkcProgressionStep[] to the existing
 *  KillChainProgression component's KillChainStage shape. The API
 *  doesn't carry a per-stage status, so we derive one: every stage in
 *  the array is "completed", and we pad up to 7 with "pending". */
function toKillChainStages(steps: CkcProgressionStep[]): KillChainStage[] {
  const FULL = ["Reconnaissance", "Weaponization", "Delivery", "Exploitation", "Installation", "Command & Control", "Actions on Objectives"]
  const seen = new Set(steps.map((s) => s.ckcStage))
  return FULL.map((name, i) => {
    const idx = i + 1
    const step = steps.find((s) => s.ckcStage === idx)
    if (step) {
      return {
        id: `ckc-${idx}`,
        name: step.ckcStageName || name,
        status: "completed" as const,
        timestamp: step.enteredAt
          ? new Date(step.enteredAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
          : undefined,
      }
    }
    return {
      id: `ckc-${idx}`,
      name,
      status: seen.size > 0 ? ("pending" as const) : ("pending" as const),
      timestamp: undefined,
    }
  })
}

interface PageProps {
  params: { id: string }
}

export default function AttackAnalysisDetailPage({ params }: PageProps) {
  const { id } = params
  const router = useRouter()

  const isLatest = id === "latest"
  const chainList = useChainList({ limit: 1 })
  const resolvedId = isLatest ? chainList.data?.items[0]?.chainId ?? null : id

  useEffect(() => {
    if (isLatest && resolvedId) {
      router.replace(`/attack-analysis/${resolvedId}`)
    }
  }, [isLatest, resolvedId, router])

  const ckcProg = useCkcProgression(resolvedId)
  const predictions = useChainPredictions(resolvedId)
  const infection = useChainInfection(resolvedId)
  const dwell = useChainDwellTime(resolvedId)

  if (isLatest) {
    const noChainsYet = chainList.isFetched && !resolvedId
    return (
      <div className="flex h-64 items-center justify-center">
        {noChainsYet ? (
          <p className="text-sm text-[var(--strix-text-muted)]">
            No attack chains yet — run a simulation to populate this view.
          </p>
        ) : (
          <Loader2 className="h-5 w-5 animate-spin text-strix-cyan" />
        )}
      </div>
    )
  }

  const currentStage = predictions.data?.currentStage ?? 0
  const maxStageReached = ckcProg.data?.stages.reduce((m, s) => Math.max(m, s.ckcStage), 0) ?? 0
  const severity = severityFromCkc(Math.max(currentStage, maxStageReached))
  // Treat as a real breach only if the chain reached a meaningful CKC
  // stage. Stage 0 / closed-as-benign chains don't warrant the red
  // "BREACH DETECTED" badge — that was the misleading thing on the
  // previous page.
  const isBreach = maxStageReached >= 2 || (dwell.data?.status === "open" && currentStage >= 1)

  // Format dwell on closed chains too — previously "—" appeared even
  // when we had a real start + close timestamp.
  const dwellLabel = dwell.data?.startedAt
    ? formatDuration(dwell.data.durationSeconds)
    : "—"

  const stages = useMemo(
    () => toKillChainStages(ckcProg.data?.stages ?? []),
    [ckcProg.data?.stages],
  )

  const isLoading = ckcProg.isLoading || predictions.isLoading

  // Pick the first infected host as the "primary host" for
  // intel-deep-link purposes.
  const primaryHost =
    infection.data?.infectedHosts?.[0]?.hostName ??
    infection.data?.infectedHosts?.[0]?.hostId ??
    null

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] text-strix-primary dark:text-strix-cyan uppercase tracking-widest font-semibold mb-1">
            FORENSIC INCIDENT REPORT
          </p>
          <h1 className="text-3xl font-black text-[var(--strix-text)] tracking-tight">
            Chain {id.slice(0, 8)}
            <br />
            <span className="text-base font-medium text-[var(--strix-text-muted)]">
              {predictions.data?.currentStageName ?? "—"} · status{" "}
              {dwell.data?.status ?? "?"}
              {dwell.data?.closeReason ? ` · ${dwell.data.closeReason}` : ""}
            </span>
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
              Threat Level
            </span>
            <span className={`inline-block px-3 py-1 rounded-md text-xs font-bold border uppercase ${severity.cls}`}>
              {severity.label}
            </span>
          </div>
          <div className="text-right">
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
              Dwell Time
            </span>
            <div className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
              <span className="text-lg font-bold text-[var(--strix-text)]">
                {dwellLabel}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Kill Chain Progression — full 7-stage view derived from API. */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-6">
        {isLoading && !ckcProg.data ? (
          <div className="flex h-32 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-strix-cyan" />
          </div>
        ) : (
          <KillChainProgression stages={stages} isBreach={isBreach} />
        )}
      </div>

      {/* Row 1: Stage Timeline (DQN actions per stage) | AI Predictions */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Target className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">Stage Timeline</h3>
            <span className="text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider">
              entries + DQN actions per stage
            </span>
          </div>
          <ChainStageTimeline stages={ckcProg.data?.stages ?? []} />
        </div>
        <div className="lg:col-span-5 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <AIPredictionsPanel
            predictions={predictions.data as never}
            hostId={primaryHost}
          />
        </div>
      </div>

      {/* Row 2: Affected Hosts | Stage probability distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">Affected Hosts</h3>
            {infection.data && (
              <span className="ml-auto text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider font-mono">
                {infection.data.infectedCount}/{infection.data.totalCount} hosts ·{" "}
                {(infection.data.percent * 100).toFixed(1)}% radius
              </span>
            )}
          </div>
          <AffectedHostsTable hosts={infection.data?.infectedHosts ?? []} />
        </div>
        <div className="lg:col-span-5 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Target className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">CKC Stage Distribution</h3>
          </div>
          <p className="text-[10px] text-[var(--strix-text-muted)] mb-3 leading-relaxed">
            Transformer's per-stage probability for this chain's next move.
            The highlighted bar is the top prediction.
          </p>
          <StageProbabilityBars
            probabilities={predictions.data?.probabilities ?? []}
            predictedNextStage={predictions.data?.predictedNextStage ?? null}
          />
        </div>
      </div>

      {/* Bottom Metrics Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Infection Radius"
          value={infection.data ? `${(infection.data.percent * 100).toFixed(1)}%` : "—"}
          sub={infection.data ? `${infection.data.infectedCount}/${infection.data.totalCount} hosts` : "—"}
        />
        <MetricCard
          label="Dwell Time"
          value={dwellLabel}
          sub={dwell.data?.status ?? "—"}
        />
        <MetricCard
          label="Predicted Next Stage"
          value={predictions.data?.predictedNextStageName ?? "—"}
          sub={predictions.data ? `confidence ${(predictions.data.confidence * 100).toFixed(0)}%` : "—"}
        />
        <MetricCard
          label="Steps in Chain"
          value={(ckcProg.data?.stages.length ?? 0).toString()}
          sub="distinct CKC stages observed"
        />
      </div>

      {/* Operator notes — local-only scratchpad. */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
        <OperatorNotes chainId={resolvedId ?? id} />
      </div>

      {/* Action Bar */}
      <div className="flex items-center justify-between bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl px-6 py-3">
        <div className="flex items-center gap-3">
          <Users className="h-4 w-4 text-[var(--strix-text-muted)]" />
          <span className="text-xs text-[var(--strix-text-muted)]">
            Chain id: <span className="font-mono">{id}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const bundle = {
                exportedAt: new Date().toISOString(),
                chainId: id,
                infection: infection.data ?? null,
                ckcProgression: ckcProg.data ?? null,
                dwellTime: dwell.data ?? null,
                predictions: predictions.data ?? null,
              }
              const stamp = new Date().toISOString().replace(/[:.]/g, "-")
              downloadJson(`strix-forensic-${id}-${stamp}.json`, bundle)
              toast.success("Forensic bundle exported (JSON).")
            }}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-semibold uppercase tracking-wider border border-[var(--strix-border)] text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-surface)] transition-colors"
          >
            <FileText className="h-3.5 w-3.5" />
            Export Forensic
          </button>
          <button
            onClick={() => {
              if (typeof window === "undefined") return
              const ok = window.confirm(
                "Initiate counter-measure on this chain? This is a manual operator action. The platform does not auto-execute network blocks; the request will be queued for approval.",
              )
              if (!ok) return
              toast.warning(
                "Counter-measure queued for approval. (Backend RL counter-measure endpoint is not enabled in this build.)",
                6000,
              )
            }}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-semibold uppercase tracking-wider bg-red-500 text-white hover:bg-red-600 transition-colors"
          >
            <Zap className="h-3.5 w-3.5" />
            Initiate Counter-Measure
          </button>
        </div>
      </div>
    </div>
  )
}

function MetricCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
      <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
        {label}
      </span>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-[var(--strix-text)]">{value}</span>
      </div>
      <span className="text-[10px] text-[var(--strix-text-muted)]">{sub}</span>
    </div>
  )
}
