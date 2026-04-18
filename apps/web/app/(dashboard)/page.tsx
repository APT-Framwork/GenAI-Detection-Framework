"use client"

import { useMemo } from "react"

import { AttackVectorChart } from "@/components/charts/attack-vector-chart"
import { CircularProgress } from "@/components/charts/circular-progress"
import { LiveAlertCard } from "@/components/feed/live-alert-card"
import { VictimGraph } from "@/components/dashboard/VictimGraph"
import {
  useAttackVector,
  useGlobalRisk,
  useSentinelInsight,
  useRefreshSentinelInsight,
} from "@/lib/api/hooks"
import { useLiveFeed, type LiveFeedEvent } from "@/lib/api/live-feed"
import { useChainList } from "@/lib/api/analysis"
import {
  ShieldAlert,
  Server,
  Link2,
  Zap,
  Brain,
  Loader2,
  AlertTriangle,
} from "lucide-react"

// Project a LiveFeedEvent into the shape `LiveAlertCard` expects.
// LiveAlertCard's existing prop type lives in apps/web/types — we keep
// this projector tiny + adaptive so a future card-component refactor
// doesn't require backend changes.
function liveEventToAlertProp(e: LiveFeedEvent) {
  return {
    id: e.alertId,
    timestamp: e.occurredAt,
    title: e.dqnActionName ? `[${e.dqnActionName}] ${e.ckcStageName}` : e.ckcStageName,
    description: e.mitreTechniques.length
      ? `MITRE ${e.mitreTechniques.join(", ")}`
      : `Agent ${e.agentId ?? "unknown"}`,
    severity: severityFromCkc(e.ckcStage),
    source: e.agentId ?? "unknown",
    mitreTactics: e.mitreTechniques,
    impact: e.dqnActionName ?? "MONITOR",
  }
}

function severityFromCkc(stage: number): "critical" | "high" | "medium" | "low" | "info" {
  if (stage >= 6) return "critical"
  if (stage >= 4) return "high"
  if (stage >= 2) return "medium"
  if (stage >= 1) return "low"
  return "info"
}

const kpiIcons = [ShieldAlert, Server, Link2, Zap]

export default function DashboardPage() {
  const attackVector = useAttackVector("1h")
  const globalRisk = useGlobalRisk("1h")
  const sentinel = useSentinelInsight()
  const refreshSentinel = useRefreshSentinelInsight()
  const liveFeed = useLiveFeed({ maxEvents: 8 })
  const chains = useChainList({ onlyOpen: true, limit: 1 })

  // Derived KPIs from live aggregates (zero is a valid value — no mock fallback).
  const kpis = useMemo(() => {
    const totalAlerts = attackVector.data?.totalAlerts ?? 0
    const openChains = chains.data?.openCount ?? 0
    const globalRiskPct = Math.round((globalRisk.data?.globalRisk ?? 0) * 100)
    return [
      { label: "Alerts (1h)", value: totalAlerts.toString(), unit: "" },
      { label: "Active chains", value: openChains.toString(), unit: "" },
      { label: "Global risk", value: globalRiskPct.toString(), unit: "%" },
      { label: "SSE", value: liveFeed.status, unit: "" },
    ]
  }, [attackVector.data, chains.data, globalRisk.data, liveFeed.status])

  const lastUpdated = attackVector.dataUpdatedAt
    ? new Date(attackVector.dataUpdatedAt).toLocaleTimeString()
    : "—"

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] text-[#00666d] dark:text-strix-cyan uppercase tracking-[1.2px] font-bold mb-1">
            LIVE SENTINEL
          </p>
          <h1 className="text-[36px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-[-0.9px] leading-tight font-[family-name:var(--font-space-grotesk)]">
            Attack Timeline
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-[0.5px]">
            Last updated: {lastUpdated}
          </span>
          <div
            className={`h-2 w-2 rounded-full animate-pulse ${
              liveFeed.status === "open" ? "bg-emerald-500" : "bg-amber-500"
            }`}
          />
        </div>
      </div>

      {/* Victim Graph (replaces KillChainTimeline per §11.1) */}
      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-[1.2px]">
            Connected Victims
          </h3>
          <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-[0.5px]">
            Window: 1 h
          </span>
        </div>
        <VictimGraph window="1h" />
      </div>

      {/* Middle Row: Attack Vector + Threat Intensity + AI Insight */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Attack Vector */}
        <div className="lg:col-span-4 bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6">
          <AttackVectorChart />
        </div>

        {/* Threat Intensity */}
        <div className="lg:col-span-3 bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6 flex flex-col items-center">
          <h3 className="text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-[1.2px] mb-4 self-start">
            Threat Intensity
          </h3>
          <CircularProgress
            value={Math.round((globalRisk.data?.globalRisk ?? 0) * 100)}
            size={150}
            strokeWidth={10}
            color="#00666d"
          />
          <p className="text-[14px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-4 text-center leading-relaxed">
            Δ1h:{" "}
            <span className="font-bold text-[#00343d] dark:text-[var(--strix-text)]">
              {globalRisk.data
                ? `${(globalRisk.data.delta1h * 100).toFixed(1)}%`
                : "—"}
            </span>{" "}
            · components from VAE / GNN / anomaly-rate.
          </p>
        </div>

        {/* AI Sentinel Insight */}
        <div className="lg:col-span-5 bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-[#00666d] dark:text-strix-cyan" />
              <h3 className="text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-[1.2px]">
                AI Sentinel Insight
              </h3>
              {sentinel.data?.stale && (
                <span className="flex items-center gap-1 text-[9px] uppercase tracking-[0.5px] text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="h-3 w-3" /> stale
                </span>
              )}
            </div>
            <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-[0.5px]">
              {sentinel.data?.modelVersion ?? "—"}
            </span>
          </div>
          <div className="bg-[#d6f6ff] dark:bg-[var(--strix-bg-surface)] rounded-[32px] p-5 flex-1">
            {sentinel.isLoading ? (
              <div className="flex h-24 items-center justify-center">
                <Loader2 className="h-5 w-5 animate-spin text-[#00666d] dark:text-strix-cyan" />
              </div>
            ) : (
              <>
                <p className="text-[14px] text-[#2b636f] dark:text-[var(--strix-text)] leading-relaxed font-[family-name:var(--font-inter)]">
                  {sentinel.data?.insight ?? "No insight available."}
                </p>
                {sentinel.data?.recommendedActions?.length ? (
                  <ul className="mt-3 space-y-1 text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    {sentinel.data.recommendedActions.slice(0, 3).map((a, i) => (
                      <li key={i}>
                        <span className="font-bold">{a.label}</span>
                        {a.rationale && ` — ${a.rationale}`}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            )}
          </div>
          <button
            type="button"
            disabled={refreshSentinel.isPending}
            onClick={() => refreshSentinel.mutate()}
            className="mt-4 w-full py-3 rounded-[9999px] text-[12px] font-bold uppercase tracking-[1.2px] bg-[#00666d] dark:bg-strix-cyan text-[#cffbff] dark:text-[#0b0e14] hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {refreshSentinel.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Refresh Insight
          </button>
        </div>
      </div>

      {/* Bottom Row: Live Feed (full width — TimelineChart removed) */}
      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-[1.2px]">
            Live Feed
          </h3>
          <div className="flex items-center gap-3">
            <span className="text-[10px] px-3 py-1 rounded-[9999px] bg-[#baf1ff] text-[#00666d] dark:bg-strix-cyan/10 dark:text-strix-cyan font-bold uppercase tracking-[0.5px]">
              {liveFeed.status.toUpperCase()}
            </span>
            <a
              href="/vigilance-feed"
              className="text-[10px] text-[#00666d] dark:text-strix-cyan font-bold uppercase tracking-[0.5px] hover:underline"
            >
              View all
            </a>
          </div>
        </div>
        {liveFeed.events.length === 0 ? (
          <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] py-8 text-center">
            Waiting for alerts… (SSE: {liveFeed.status})
          </p>
        ) : (
          <div className="space-y-0">
            {liveFeed.events.slice(0, 6).map((e) => (
              <LiveAlertCard
                key={e.id}
                alert={liveEventToAlertProp(e.data) as never}
                compact
              />
            ))}
          </div>
        )}
      </div>

      {/* Bottom KPI Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi, i) => {
          const Icon = kpiIcons[i] ?? ShieldAlert
          return (
            <div
              key={kpi.label}
              className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6 flex items-center gap-4"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-[32px] bg-[rgba(0,102,109,0.1)] dark:bg-strix-cyan/10">
                <Icon className="h-5 w-5 text-[#00666d] dark:text-strix-cyan" />
              </div>
              <div>
                <span className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                  {kpi.value}
                </span>
                <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-[1px]">
                  {kpi.label}
                  {kpi.unit && ` · ${kpi.unit}`}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
