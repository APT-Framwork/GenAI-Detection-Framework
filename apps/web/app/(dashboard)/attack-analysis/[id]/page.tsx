"use client"

import { useMemo } from "react"

import { AIPredictionsPanel } from "@/components/charts/ai-predictions-panel"
import { ForensicLogViewer } from "@/components/charts/forensic-log-viewer"
import { GraphEvolution } from "@/components/charts/graph-evolution"
import { KillChainProgression } from "@/components/charts/kill-chain-progression"
import {
  useChainDwellTime,
  useChainGraphEvolution,
  useChainInfection,
  useChainLogs,
  useChainPredictions,
  useCkcProgression,
} from "@/lib/api/analysis"
import {
  Clock,
  FileText,
  Loader2,
  Users,
  Zap,
} from "lucide-react"

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—"
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`
  if (m > 0) return `${m}m ${String(s).padStart(2, "0")}s`
  return `${s}s`
}

function severityFromCkc(stage: number): { label: string; cls: string } {
  if (stage >= 6)
    return {
      label: "Critical",
      cls: "bg-red-500/10 text-red-500 border-red-500/20",
    }
  if (stage >= 4)
    return {
      label: "High",
      cls: "bg-orange-500/10 text-orange-500 border-orange-500/20",
    }
  if (stage >= 2)
    return {
      label: "Medium",
      cls: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
    }
  return { label: "Low", cls: "bg-cyan-500/10 text-cyan-600 border-cyan-500/20" }
}

interface PageProps {
  params: { id: string }
}

export default function AttackAnalysisDetailPage({ params }: PageProps) {
  const { id } = params

  const ckcProg = useCkcProgression(id)
  const graphEvo = useChainGraphEvolution(id)
  const predictions = useChainPredictions(id)
  const infection = useChainInfection(id)
  const dwell = useChainDwellTime(id)
  const logsQuery = useChainLogs(id, 50)

  const flatLogs = useMemo(() => {
    const pages = logsQuery.data?.pages ?? []
    return pages.flatMap((p) => p.items)
  }, [logsQuery.data])

  const severity = severityFromCkc(predictions.data?.currentStage ?? 0)
  const dwellLabel =
    dwell.data && dwell.data.startedAt
      ? formatDuration(dwell.data.durationSeconds)
      : "—"

  const isLoading =
    ckcProg.isLoading || graphEvo.isLoading || predictions.isLoading

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
            </span>
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
              Threat Level
            </span>
            <span
              className={`inline-block px-3 py-1 rounded-md text-xs font-bold border uppercase ${severity.cls}`}
            >
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

      {/* Kill Chain Progression — DQN-actioned stages */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-6">
        {isLoading && !ckcProg.data ? (
          <div className="flex h-32 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-strix-cyan" />
          </div>
        ) : (
          <KillChainProgression stages={(ckcProg.data?.stages ?? []) as never} />
        )}
      </div>

      {/* Graph Evolution + AI Predictions */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <GraphEvolution snapshots={graphEvo.data?.snapshots as never} />
        </div>
        <div className="lg:col-span-5 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <AIPredictionsPanel predictions={predictions.data as never} />
        </div>
      </div>

      {/* Forensic Logs (paged + live-tail capable) */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[12px] font-bold text-[var(--strix-text)] uppercase tracking-[1.2px]">
            Forensic Logs
          </h3>
          <button
            type="button"
            disabled={!logsQuery.hasNextPage || logsQuery.isFetchingNextPage}
            onClick={() => logsQuery.fetchNextPage()}
            className="text-[10px] text-strix-primary dark:text-strix-cyan font-bold uppercase tracking-[0.5px] hover:underline disabled:opacity-50"
          >
            {logsQuery.hasNextPage ? "Load older" : "All loaded"}
          </button>
        </div>
        <ForensicLogViewer logs={flatLogs as never} />
      </div>

      {/* Bottom Metrics Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Infection Radius"
          value={
            infection.data
              ? `${(infection.data.percent * 100).toFixed(1)}%`
              : "—"
          }
          sub={
            infection.data
              ? `${infection.data.infectedCount}/${infection.data.totalCount} hosts`
              : "—"
          }
        />
        <MetricCard
          label="Dwell Time"
          value={dwellLabel}
          sub={dwell.data?.status ?? "—"}
        />
        <MetricCard
          label="Predicted Next Stage"
          value={predictions.data?.predictedNextStageName ?? "—"}
          sub={
            predictions.data
              ? `confidence ${(predictions.data.confidence * 100).toFixed(0)}%`
              : "—"
          }
        />
        <MetricCard
          label="Steps in Chain"
          value={(ckcProg.data?.stages.length ?? 0).toString()}
          sub="distinct CKC stages observed"
        />
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
          <button className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-semibold uppercase tracking-wider border border-[var(--strix-border)] text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-surface)] transition-colors">
            <FileText className="h-3.5 w-3.5" />
            Export Forensic PDF
          </button>
          <button className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-semibold uppercase tracking-wider bg-red-500 text-white hover:bg-red-600 transition-colors">
            <Zap className="h-3.5 w-3.5" />
            Initiate Counter-Measure
          </button>
        </div>
      </div>
    </div>
  )
}

function MetricCard({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub: string
}) {
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
