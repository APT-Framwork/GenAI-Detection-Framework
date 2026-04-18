"use client"

import { useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { cn } from "@/lib/utils"

import { useLiveFeed, type LiveFeedEvent } from "@/lib/api/live-feed"
import { useChainList } from "@/lib/api/analysis"
import {
  Filter,
  CheckCheck,
  Diamond,
  AlertTriangle,
  ShieldCheck,
  CheckCircle2,
  Wifi,
  Activity,
} from "lucide-react"

function severityFromCkc(stage: number): "critical" | "high" | "medium" | "low" | "info" {
  if (stage >= 6) return "critical"
  if (stage >= 4) return "high"
  if (stage >= 2) return "medium"
  if (stage >= 1) return "low"
  return "info"
}

function liveEventToAlert(e: LiveFeedEvent) {
  const severity = severityFromCkc(e.ckcStage)
  return {
    id: e.alertId,
    timestamp: e.occurredAt,
    title: `${e.ckcStageName}${e.dqnActionName ? ` · ${e.dqnActionName}` : ""}`,
    description:
      e.mitreTechniques.length > 0
        ? `MITRE ${e.mitreTechniques.join(", ")}`
        : `Agent ${e.agentId ?? "unknown"}`,
    severity,
    source: e.agentId ?? "unknown",
  }
}

// Replaced by useLiveFeed() inside the component
const feedAlerts: ReturnType<typeof liveEventToAlert>[] = []

// Badge config per severity
const badgeConfig: Record<
  string,
  { label: string; bg: string; text: string; darkBg: string; darkText: string }
> = {
  critical: {
    label: "CRITICAL THREAT",
    bg: "bg-[#fb5151]",
    text: "text-[#570008]",
    darkBg: "dark:bg-red-500/20",
    darkText: "dark:text-red-400",
  },
  medium: {
    label: "SYSTEM WARNING",
    bg: "bg-[#fff4d6]",
    text: "text-[#855e00]",
    darkBg: "dark:bg-amber-500/20",
    darkText: "dark:text-amber-400",
  },
  high: {
    label: "SYSTEM WARNING",
    bg: "bg-[#fff4d6]",
    text: "text-[#855e00]",
    darkBg: "dark:bg-amber-500/20",
    darkText: "dark:text-amber-400",
  },
  info: {
    label: "INTEL UPDATE",
    bg: "bg-[#72b5ff]",
    text: "text-[#003259]",
    darkBg: "dark:bg-blue-500/20",
    darkText: "dark:text-blue-400",
  },
  low: {
    label: "RESOLVED",
    bg: "bg-emerald-100",
    text: "text-emerald-800",
    darkBg: "dark:bg-emerald-500/20",
    darkText: "dark:text-emerald-400",
  },
}

function SeverityIcon({ severity }: { severity: string }) {
  switch (severity) {
    case "critical":
      return (
        <div className="flex h-[48px] w-[48px] items-center justify-center rounded-full bg-red-50 dark:bg-red-500/10">
          <Diamond className="h-5 w-5 text-[#b31b25] dark:text-red-400" />
        </div>
      )
    case "medium":
    case "high":
      return (
        <div className="flex h-[48px] w-[48px] items-center justify-center rounded-full bg-amber-50 dark:bg-amber-500/10">
          <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
        </div>
      )
    case "info":
      return (
        <div className="flex h-[48px] w-[48px] items-center justify-center rounded-full bg-blue-50 dark:bg-blue-500/10">
          <ShieldCheck className="h-5 w-5 text-[#005ea0] dark:text-blue-400" />
        </div>
      )
    case "low":
      return (
        <div className="flex h-[48px] w-[48px] items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-500/10">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
        </div>
      )
    default:
      return null
  }
}

export default function VigilanceFeedPage() {
  const router = useRouter()
  const [filter, setFilter] = useState<string>("all")
  const liveFeed = useLiveFeed({ maxEvents: 200 })
  const chains = useChainList({ onlyOpen: true, limit: 1 })
  void chains // header may consume in future iteration

  // Project SSE events through the existing alert shape so the JSX below
  // stays unchanged.
  const allAlerts = useMemo(
    () => liveFeed.events.map((e) => liveEventToAlert(e.data)),
    [liveFeed.events],
  )

  const alerts =
    filter === "all"
      ? allAlerts
      : allAlerts.filter((a) => a.severity === filter)

  const criticalCount = allAlerts.filter((a) => a.severity === "critical").length
  const warningCount = allAlerts.filter(
    (a) => a.severity === "medium" || a.severity === "high",
  ).length
  const updateCount = allAlerts.filter(
    (a) => a.severity === "info" || a.severity === "low",
  ).length

  // No-op acknowledge while we don't have a backend ack endpoint yet —
  // future P5+ ticket will wire `POST /alerts/{id}/ack`.
  const acknowledgeAlert = (_id: string) => {}

  return (
    <div className="space-y-[24px]">
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[1.2px] text-[#00666d] dark:text-[var(--strix-text-muted)] mb-[6px]">
            SENTINEL ACTIVITY
          </p>
          <h1 className="text-[48px] font-bold leading-[1.05] tracking-[-2.4px] text-[#00343d] dark:text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk)]">
            Live Security
            <br />
            <span className="text-[#00666d] dark:text-[var(--strix-text-muted)]">
              Orchestration.
            </span>
          </h1>
        </div>
        <div className="flex items-center gap-[12px] pt-[12px]">
          <button
            onClick={() => setFilter(filter === "all" ? "critical" : "all")}
            className="flex items-center gap-[8px] rounded-[9999px] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] bg-white dark:bg-[var(--strix-bg-card)] px-[24px] py-[10px] text-[12px] font-semibold uppercase tracking-[0.6px] text-[#00343d] dark:text-[var(--strix-text)] hover:bg-gray-50 dark:hover:bg-[var(--strix-bg-surface)] transition-colors"
          >
            <Filter className="h-[14px] w-[14px]" />
            Filter Feed
          </button>
          <button className="flex items-center gap-[8px] rounded-[9999px] bg-[#00666d] px-[24px] py-[10px] text-[12px] font-semibold uppercase tracking-[0.6px] text-[#cffbff] hover:opacity-90 transition-opacity">
            <CheckCheck className="h-[14px] w-[14px]" />
            Acknowledge All
          </button>
        </div>
      </div>

      {/* ── Main Grid ──────────────────────────────────────── */}
      <div className="grid grid-cols-12 gap-[24px]">
        {/* ── Left Column (col 1-3) ──────────────────────── */}
        <div className="col-span-12 lg:col-span-3 space-y-[24px]">
          {/* Live Status Card */}
          <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-[24px]">
            <h3 className="text-[13px] font-bold uppercase tracking-[1px] text-[#00343d] dark:text-[var(--strix-text)] mb-[20px]">
              LIVE STATUS
            </h3>
            <div className="space-y-[16px]">
              {/* Critical */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-[10px]">
                  <div className="h-[6px] w-[32px] rounded-full bg-[#b31b25]" />
                  <span className="text-[14px] text-[#00343d] dark:text-[var(--strix-text)]">
                    Critical
                  </span>
                </div>
                <span className="rounded-[9999px] bg-[#b31b25] px-[12px] py-[3px] text-[12px] font-bold text-white">
                  {String(criticalCount).padStart(2, "0")}
                </span>
              </div>
              {/* Warnings */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-[10px]">
                  <div className="h-[6px] w-[32px] rounded-full bg-amber-500" />
                  <span className="text-[14px] text-[#00343d] dark:text-[var(--strix-text)]">
                    Warnings
                  </span>
                </div>
                <span className="rounded-[9999px] bg-amber-500 px-[12px] py-[3px] text-[12px] font-bold text-white">
                  {String(warningCount).padStart(2, "0")}
                </span>
              </div>
              {/* Updates */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-[10px]">
                  <div className="h-[6px] w-[32px] rounded-full bg-[#00666d]" />
                  <span className="text-[14px] text-[#00343d] dark:text-[var(--strix-text)]">
                    Updates
                  </span>
                </div>
                <span className="rounded-[9999px] bg-[#00666d] px-[12px] py-[3px] text-[12px] font-bold text-[#cffbff]">
                  {String(updateCount).padStart(2, "0")}
                </span>
              </div>
            </div>
          </div>

          {/* Generate Threat Report Card */}
          <div className="relative h-[200px] rounded-[48px] overflow-clip">
            <div className="absolute inset-0 bg-gradient-to-br from-[#1a2e3a] to-[#0d1a20]" />
            {/* Abstract background decoration */}
            <div className="absolute inset-0 opacity-[0.08]">
              <div className="absolute top-[20%] left-[10%] h-[120px] w-[120px] rounded-full border border-white/20" />
              <div className="absolute top-[40%] right-[5%] h-[80px] w-[80px] rounded-full border border-white/30" />
              <div className="absolute bottom-[10%] left-[30%] h-[60px] w-[1px] bg-white/40 rotate-45" />
            </div>
            <div className="relative flex flex-col justify-end h-full p-[28px]">
              <h4 className="text-[18px] font-bold text-white leading-tight">
                Generate Threat
                <br />
                Report
              </h4>
              <p className="text-[11px] font-medium uppercase tracking-[0.8px] text-white/60 mt-[8px]">
                STRIX AI ANALYSIS
              </p>
            </div>
          </div>
        </div>

        {/* ── Right Column (col 4-12) ────────────────────── */}
        <div className="col-span-12 lg:col-span-9 space-y-[20px]">
          {alerts.map((alert) => {
            const badge = badgeConfig[alert.severity] ?? badgeConfig.info
            const isResolved = alert.status === "acknowledged" || alert.severity === "low"

            return (
              <div
                key={alert.id}
                className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-[32px]"
              >
                {/* Top row: icon + badge + time */}
                <div className="flex items-center justify-between mb-[16px]">
                  <div className="flex items-center gap-[14px]">
                    <SeverityIcon severity={alert.severity} />
                    <span
                      className={cn(
                        "rounded-[9999px] px-[12px] py-[4px] text-[10px] font-bold uppercase tracking-[0.6px]",
                        badge.bg,
                        badge.text,
                        badge.darkBg,
                        badge.darkText
                      )}
                    >
                      {badge.label}
                    </span>
                  </div>
                  <span className="text-[13px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    {alert.timestamp}
                  </span>
                </div>

                {/* Title */}
                <h3 className="text-[20px] font-bold text-[#00343d] dark:text-[var(--strix-text)] mb-[8px]">
                  {alert.title}
                </h3>

                {/* Description */}
                <p className="text-[16px] leading-[1.6] text-[#2b636f] dark:text-[var(--strix-text-muted)] font-[family-name:var(--font-inter)] mb-[4px]">
                  {alert.description}
                </p>

                {/* IP if present */}
                {alert.ip && (
                  <p className="text-[14px] font-mono text-[#2b636f] dark:text-[var(--strix-text-muted)] mt-[4px] mb-[8px]">
                    {alert.ip}
                  </p>
                )}

                {/* Action buttons */}
                {!isResolved && (
                  <div className="flex items-center gap-[12px] mt-[20px]">
                    <button
                      onClick={() => {
                        if (alert.severity === "info") {
                          // "VIEW DETAILS" for intel updates
                        } else {
                          router.push(`/attack-analysis/${alert.id}`)
                        }
                      }}
                      className="rounded-[9999px] bg-[#00666d] px-[20px] py-[10px] text-[11px] font-bold uppercase tracking-[0.8px] text-[#cffbff] hover:opacity-90 transition-opacity"
                    >
                      {alert.severity === "info" ? "VIEW DETAILS" : "GO TO CASE"}
                    </button>
                    <button
                      onClick={() => acknowledgeAlert(alert.id)}
                      className="rounded-[9999px] border border-[rgba(128,182,195,0.25)] dark:border-[var(--strix-border)] px-[20px] py-[10px] text-[11px] font-bold uppercase tracking-[0.8px] text-[#00343d] dark:text-[var(--strix-text)] hover:bg-gray-50 dark:hover:bg-[var(--strix-bg-surface)] transition-colors"
                    >
                      ACKNOWLEDGE
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Bottom Status Bar ──────────────────────────────── */}
      <div className="flex items-center justify-between bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] px-[24px] py-[16px]">
        <div className="flex items-center gap-[32px]">
          <div className="flex items-center gap-[8px]">
            <span className="text-[10px] font-semibold uppercase tracking-[0.8px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              SSE
            </span>
            <span className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
              {liveFeed.status}
            </span>
          </div>
          <div className="flex items-center gap-[8px]">
            <span className="text-[10px] font-semibold uppercase tracking-[0.8px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              EVENTS BUFFERED
            </span>
            <span className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
              {liveFeed.events.length.toLocaleString()}
            </span>
          </div>
          <div className="flex items-center gap-[8px]">
            <span className="text-[10px] font-semibold uppercase tracking-[0.8px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              OPEN CHAINS
            </span>
            <span className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
              {chains.data?.openCount ?? 0}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-[8px]">
          <div
            className={`h-[8px] w-[8px] rounded-full animate-pulse ${
              liveFeed.status === "open" ? "bg-emerald-500" : "bg-amber-500"
            }`}
          />
          <Activity className="h-[18px] w-[18px] text-[#00666d] dark:text-emerald-400" />
        </div>
      </div>
    </div>
  )
}
