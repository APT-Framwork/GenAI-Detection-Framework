"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

import { AIPredictionsPanel } from "@/components/charts/ai-predictions-panel"
import { ChainStageTimeline } from "@/components/charts/chain-stage-timeline"
import { AffectedHostsTable } from "@/components/charts/affected-hosts-table"
import { ChainTimeline } from "@/components/chains/chain-timeline"
import { PersistedNotes } from "@/components/chains/persisted-notes"
import { TagPicker } from "@/components/chains/tag-picker"
import { TlpPicker } from "@/components/chains/tlp-picker"
import { PlaybookViewer } from "@/components/playbooks/playbook-viewer"
import {
  useChainDwellTime,
  useChainInfection,
  useChainList,
  useChainLiveRefresh,
  useChainPredictions,
  useCkcProgression,
} from "@/lib/api/analysis"
import { downloadJson } from "@/lib/download"
import { toast } from "@/lib/toast"
import {
  Clock,
  FileText,
  Loader2,
  Target,
  Users,
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

  // Live-refresh: SSE-driven invalidation of all panels above whenever a
  // new alert lands on this chain. Without this the page would poll on a
  // 5 s interval and feel laggy during a simulation.
  useChainLiveRefresh(resolvedId)

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
  // Format dwell on closed chains too — previously "—" appeared even
  // when we had a real start + close timestamp.
  const dwellLabel = dwell.data?.startedAt
    ? formatDuration(dwell.data.durationSeconds)
    : "—"

  // Pick the first infected host as the "primary host" for
  // intel-deep-link purposes.
  const primaryHost =
    infection.data?.infectedHosts?.[0]?.hostName ??
    infection.data?.infectedHosts?.[0]?.hostId ??
    null

  return (
    <div className="flex gap-5">
      <div className="flex-1 min-w-0 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] text-strix-primary dark:text-strix-cyan uppercase tracking-widest font-semibold mb-1 flex items-center gap-2">
            <span>FORENSIC INCIDENT REPORT</span>
            {resolvedId && <TlpPicker chainId={resolvedId} />}
          </div>
          <h1 className="text-3xl font-black text-[var(--strix-text)] tracking-tight">
            Chain {id.slice(0, 8)}
            <br />
            <span className="text-base font-medium text-[var(--strix-text-muted)]">
              {predictions.data?.currentStageName ?? "—"} · status{" "}
              {dwell.data?.status ?? "?"}
              {dwell.data?.closeReason ? ` · ${dwell.data.closeReason}` : ""}
            </span>
          </h1>
          {resolvedId && (
            <div className="mt-2">
              <TagPicker chainId={resolvedId} />
            </div>
          )}
        </div>
        <div className="flex items-center gap-4 shrink-0">
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

      {/* Row 1: Stage Timeline (DQN actions per stage) | AI Predictions */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Target className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">Stage Timeline</h3>
            <span className="text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider">
              entries + STRIX actions per stage
            </span>
          </div>
          <ChainStageTimeline stages={ckcProg.data?.stages ?? []} />
        </div>
        <div className="lg:col-span-5 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <AIPredictionsPanel
            predictions={predictions.data as never}
            hostId={primaryHost}
            chainId={resolvedId}
          />
        </div>
      </div>

      {/* Affected Hosts — full width. The table lists every host that
          generated alerts on this chain; the header counts how many of
          those crossed the §6.3 infection threshold. */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Users className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
          <h3 className="text-sm font-bold text-[var(--strix-text)]">Affected Hosts</h3>
          {infection.data && (
            <span className="ml-auto text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider font-mono">
              {infection.data.infectedCount}/{infection.data.totalCount} infected ·{" "}
              {(infection.data.percent * 100).toFixed(1)}% radius
            </span>
          )}
        </div>
        <AffectedHostsTable hosts={infection.data?.infectedHosts ?? []} />
      </div>

      {/* Investigation surface — case timeline (engine + operator) left,
          backend-persisted notes right. */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          {resolvedId && <ChainTimeline chainId={resolvedId} />}
        </div>
        <div className="lg:col-span-5 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          {resolvedId && <PersistedNotes chainId={resolvedId} />}
        </div>
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
        </div>
      </div>
      </div>

      {/* Right rail — playbook viewer (hidden below xl). */}
      <aside className="w-[320px] shrink-0 hidden xl:block">
        <PlaybookViewer
          chainId={resolvedId}
          stage={Math.max(currentStage, maxStageReached)}
          technique={null}
        />
      </aside>
    </div>
  )
}

