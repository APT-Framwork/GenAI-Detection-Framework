"use client"

import { useMemo, useState } from "react"
import {
  Filter,
  Diamond,
  AlertTriangle,
  ChevronDown,
  Zap,
  Activity,
  Map,
} from "lucide-react"
import { cn } from "@/lib/utils"

import { useNotifications, type InterventionItem } from "@/lib/api/analysis"
import { useTopology } from "@/lib/api/topology"

function severityFromAction(name: string): "critical" | "warning" | "info" {
  if (name === "BLOCK_USER_IP" || name === "ISOLATE_HOST") return "critical"
  if (name === "ESCALATE") return "warning"
  return "info"
}

function timeAgo(iso: string): string {
  const dt = Date.parse(iso)
  if (Number.isNaN(dt)) return iso
  const seconds = Math.max(0, (Date.now() - dt) / 1000)
  if (seconds < 60) return `${Math.floor(seconds)}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

function projectNotification(item: InterventionItem) {
  const severity = severityFromAction(item.actionName)
  const badge =
    severity === "critical"
      ? "Critical Intervention"
      : severity === "warning"
      ? "Escalation Issued"
      : "Sentinel Update"
  return {
    id: item.actionId,
    severity,
    badge,
    title: `${item.actionName.replace(/_/g, " ")} on ${item.agentName ?? item.hostId.slice(0, 8)}`,
    time: timeAgo(item.decidedAt),
    description: `STRIX decided ${item.actionName} at CKC stage ${item.ckcStageName}. ${
      item.requiresApproval
        ? "Pending operator approval — Apply / Reject in the Analysis tab."
        : "Auto-applied — see audit log for details."
    }`,
    actions: item.requiresApproval
      ? [
          { label: "Go to Case", primary: true, href: `/attack-analysis/${item.chainId}` },
          { label: "Acknowledge", primary: false },
        ]
      : [{ label: "Go to Case", primary: true, href: `/attack-analysis/${item.chainId}` }],
  }
}

const severityStyles = {
  critical: {
    border: "bg-[#b31b25]",
    badgeBg: "bg-[#fb5151]",
    badgeText: "text-[#570008]",
    darkBorder: "dark:bg-red-500",
    darkBadgeBg: "dark:bg-red-500/20",
    darkBadgeText: "dark:text-red-300",
  },
  warning: {
    border: "bg-[#ffb700]",
    badgeBg: "bg-[#fff4d6]",
    badgeText: "text-[#855e00]",
    darkBorder: "dark:bg-amber-500",
    darkBadgeBg: "dark:bg-amber-500/20",
    darkBadgeText: "dark:text-amber-300",
  },
  info: {
    border: "bg-[#005ea0]",
    badgeBg: "bg-[#72b5ff]",
    badgeText: "text-[#003259]",
    darkBorder: "dark:bg-blue-500",
    darkBadgeBg: "dark:bg-blue-500/20",
    darkBadgeText: "dark:text-blue-300",
  },
}

const severityIcon = {
  critical: Diamond,
  warning: AlertTriangle,
  info: Zap,
}

/* ---------- components ---------- */

type ProjectedNotification = ReturnType<typeof projectNotification>

function NotificationCard({
  notification,
}: {
  notification: ProjectedNotification
}) {
  const s = severityStyles[notification.severity]
  const Icon = severityIcon[notification.severity]

  return (
    <div className="relative bg-white dark:bg-white/5 rounded-[48px] p-[32px] overflow-clip">
      {/* left accent bar */}
      <div
        className={cn(
          "absolute left-0 top-0 bottom-0 w-[6px]",
          s.border,
          s.darkBorder
        )}
      />

      <div className="flex flex-col gap-[16px] pl-[16px]">
        {/* top row: icon + badge + time */}
        <div className="flex items-center gap-[12px] flex-wrap">
          <Icon
            className={cn(
              "h-5 w-5 flex-shrink-0",
              notification.severity === "critical"
                ? "text-[#b31b25] dark:text-red-400"
                : notification.severity === "warning"
                ? "text-[#ffb700] dark:text-amber-400"
                : "text-[#005ea0] dark:text-blue-400"
            )}
          />
          <span
            className={cn(
              "rounded-[9999px] px-[12px] py-[4px] text-[10px] font-bold uppercase leading-none",
              s.badgeBg,
              s.badgeText,
              s.darkBadgeBg,
              s.darkBadgeText
            )}
          >
            {notification.badge}
          </span>
          <span className="text-[12px] uppercase tracking-[1.2px] text-[#497f8b] dark:text-slate-400 ml-auto">
            {notification.time}
          </span>
        </div>

        {/* title */}
        <h3 className="text-[20px] font-bold text-[#00343d] dark:text-white leading-tight">
          {notification.title}
        </h3>

        {/* description */}
        <p className="text-[16px] font-medium text-[#2b636f] dark:text-slate-300 leading-relaxed font-[Inter,sans-serif]">
          {notification.description}
        </p>

        {/* actions */}
        <div className="flex items-center gap-[12px] pt-[4px]">
          {notification.actions.map((action) => (
            <button
              key={action.label}
              className={cn(
                "rounded-[9999px] px-[24px] py-[10px] text-[12px] font-bold uppercase tracking-[1.2px] transition-opacity hover:opacity-80",
                action.primary
                  ? "bg-[#00666d] text-[#cffbff] dark:bg-cyan-600 dark:text-cyan-50"
                  : "bg-[#d6f6ff] text-[#2b636f] dark:bg-white/10 dark:text-slate-300"
              )}
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ---------- page ---------- */

export default function NotificationsPage() {
  const [_filterOpen, setFilterOpen] = useState(false)
  const interventions = useNotifications(50)
  const topology = useTopology("24h")
  const notifications = useMemo(
    () => (interventions.data?.items ?? []).map(projectNotification),
    [interventions.data],
  )

  // Replace the previous hardcoded "1,240 medical devices / 4 surgical
  // theaters" copy with real values from the topology endpoint.
  const monitoredHosts = topology.data?.nodes?.length ?? 0
  const compromisedHosts = (topology.data?.nodes ?? []).filter(
    (n) => n.status === "compromised",
  ).length
  const healthScore = monitoredHosts === 0 ? 100 : Math.max(0, 100 - (compromisedHosts / monitoredHosts) * 100)
  const activeProbes = (topology.data?.edges ?? []).length

  return (
    <div className="space-y-[32px]">
      {/* ====== Header ====== */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-[48px] font-bold tracking-[-2.4px] text-[#00343d] dark:text-white leading-none font-[Space_Grotesk,sans-serif]">
            VIGILANCE FEED
          </h1>
          <p className="text-[16px] font-medium text-[#497f8b] dark:text-slate-400 mt-[8px] font-[Inter,sans-serif]">
            Real-time clinical threat intelligence and incident response.
          </p>
        </div>
        <div className="flex items-center gap-[12px]">
          <button
            onClick={() => setFilterOpen((v) => !v)}
            className="flex items-center gap-[8px] bg-white dark:bg-white/10 rounded-[9999px] px-[24px] py-[10px] text-[12px] font-bold uppercase tracking-[1.2px] text-[#00343d] dark:text-slate-200 border border-[rgba(128,182,195,0.15)] hover:shadow-sm transition-shadow"
          >
            <Filter className="h-4 w-4" />
            Filter Feed
          </button>
          <button className="rounded-[9999px] px-[24px] py-[10px] text-[12px] font-bold uppercase tracking-[1.2px] bg-[#00666d] text-[#cffbff] dark:bg-cyan-600 dark:text-cyan-50 hover:opacity-80 transition-opacity">
            Clear All
          </button>
        </div>
      </div>

      {/* ====== Feed ====== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-[24px]">
        <div className="lg:col-span-12 space-y-[24px]">
          {notifications.map((n) => (
            <NotificationCard key={n.id} notification={n} />
          ))}

          {/* Load History */}
          <div className="flex items-center justify-center gap-[8px] py-[16px]">
            <span className="text-[12px] font-bold uppercase tracking-[3.6px] text-[#497f8b] dark:text-slate-500">
              Load History
            </span>
            <ChevronDown className="h-4 w-4 text-[#497f8b] dark:text-slate-500" />
          </div>
        </div>
      </div>

      {/* ====== Sentinel Orchestration Section ====== */}
      <div className="bg-[#d6f6ff] dark:bg-white/5 rounded-[48px] p-[48px] pt-[64px] overflow-clip">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-[48px]">
          {/* left text */}
          <div className="space-y-[24px]">
            <h2 className="text-[36px] font-bold tracking-[-1.8px] text-[#00343d] dark:text-white leading-tight font-[Space_Grotesk,sans-serif]">
              SENTINEL
              <br />
              ORCHESTRATION
            </h2>
            <p className="text-[18px] font-medium text-[#2b636f] dark:text-slate-300 leading-relaxed font-[Inter,sans-serif]">
              {monitoredHosts > 0
                ? `Sentinel network is monitoring ${monitoredHosts.toLocaleString()} hosts. ${
                    compromisedHosts > 0
                      ? `${compromisedHosts} currently flagged as compromised.`
                      : "No active compromise indicators."
                  }`
                : "Sentinel network is online. No topology snapshot yet — start a simulation or inject traffic to populate."}
            </p>

            {/* stats row */}
            <div className="flex items-start gap-[48px] pt-[8px]">
              <div>
                <span className="text-[12px] font-medium uppercase tracking-[1.2px] text-[#497f8b] dark:text-slate-400">
                  Health Score
                </span>
                <div className="text-[30px] font-bold text-[#00666d] dark:text-cyan-400 leading-tight">
                  {healthScore.toFixed(1)}%
                </div>
              </div>
              <div>
                <span className="text-[12px] font-medium uppercase tracking-[1.2px] text-[#497f8b] dark:text-slate-400">
                  Active Probes
                </span>
                <div className="text-[30px] font-bold text-[#00666d] dark:text-cyan-400 leading-tight">
                  {activeProbes}
                </div>
              </div>
            </div>
          </div>

          {/* right visualization placeholder */}
          <div className="relative bg-white dark:bg-white/5 rounded-[48px] shadow-lg min-h-[280px] overflow-hidden flex items-center justify-center">
            {/* abstract map grid */}
            <div className="absolute inset-0 opacity-[0.06] dark:opacity-[0.1]">
              <svg
                className="h-full w-full"
                viewBox="0 0 400 280"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                {/* grid lines */}
                {Array.from({ length: 10 }).map((_, i) => (
                  <line
                    key={`h-${i}`}
                    x1="0"
                    y1={i * 30}
                    x2="400"
                    y2={i * 30}
                    stroke="#00666d"
                    strokeWidth="1"
                  />
                ))}
                {Array.from({ length: 14 }).map((_, i) => (
                  <line
                    key={`v-${i}`}
                    x1={i * 30}
                    y1="0"
                    x2={i * 30}
                    y2="280"
                    stroke="#00666d"
                    strokeWidth="1"
                  />
                ))}
              </svg>
            </div>

            {/* map icon */}
            <Map className="h-16 w-16 text-[#00666d]/20 dark:text-cyan-500/20" />

            {/* status panel overlay */}
            <div className="absolute bottom-[16px] right-[16px] bg-white dark:bg-slate-800 rounded-[16px] shadow-md p-[16px] space-y-[10px] min-w-[200px]">
              <div className="flex items-center gap-[8px]">
                <span className="h-[8px] w-[8px] rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-[12px] font-medium text-[#00343d] dark:text-slate-200">
                  Theater 1-A Active
                </span>
              </div>
              <div className="flex items-center gap-[8px]">
                <span className="h-[8px] w-[8px] rounded-full bg-[#b31b25] dark:bg-red-500 animate-pulse" />
                <span className="text-[12px] font-medium text-[#00343d] dark:text-slate-200">
                  Sensor Node 04 Alert
                </span>
              </div>
            </div>

            {/* decorative activity line */}
            <Activity className="absolute top-[20px] left-[20px] h-6 w-6 text-[#00666d]/30 dark:text-cyan-500/30" />
          </div>
        </div>
      </div>
    </div>
  )
}
