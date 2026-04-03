"use client"

import {
  dashboardKPIs,
  killChainStages,
  timelineEvents,
  mockAlerts,
} from "@/lib/mock-data"
import { KillChainTimeline } from "@/components/charts/kill-chain-timeline"
import { AttackVectorChart } from "@/components/charts/attack-vector-chart"
import { CircularProgress } from "@/components/charts/circular-progress"
import { TimelineChart } from "@/components/charts/timeline-chart"
import { LiveAlertCard } from "@/components/feed/live-alert-card"
import { cn } from "@/lib/utils"
import {
  ShieldAlert,
  Server,
  Link2,
  Zap,
  Brain,
  Shield,
  Activity,
} from "lucide-react"

const kpiIcons = [ShieldAlert, Server, Link2, Zap]

export default function DashboardPage() {
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
            Last updated: 2 min ago
          </span>
          <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
        </div>
      </div>

      {/* Kill Chain Timeline */}
      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-8">
        <KillChainTimeline stages={killChainStages} />
      </div>

      {/* Middle Row: Attack Vector + Threat Intensity + AI Insight */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Attack Vector Graph */}
        <div className="lg:col-span-4 bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6">
          <AttackVectorChart />
        </div>

        {/* Threat Intensity */}
        <div className="lg:col-span-3 bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6 flex flex-col items-center">
          <h3 className="text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-[1.2px] mb-4 self-start">
            Threat Intensity
          </h3>
          <CircularProgress
            value={74}
            size={150}
            strokeWidth={10}
            color="#00666d"
          />
          <p className="text-[14px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-4 text-center leading-relaxed">
            System vulnerability increased by{" "}
            <span className="font-bold text-[#00343d] dark:text-[var(--strix-text)]">12%</span>{" "}
            in the last 8 hours due to delivery attempts.
          </p>
        </div>

        {/* AI Sentinel Insight */}
        <div className="lg:col-span-5 bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <Brain className="h-4 w-4 text-[#00666d] dark:text-strix-cyan" />
            <h3 className="text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-[1.2px]">
              AI Sentinel Insight
            </h3>
          </div>
          <div className="bg-[#d6f6ff] dark:bg-[var(--strix-bg-surface)] rounded-[32px] p-5 flex-1">
            <p className="text-[14px] text-[#2b636f] dark:text-[var(--strix-text)] leading-relaxed font-[family-name:var(--font-inter)]">
              &quot;Pattern matches APT-29 signature. The delivery phase is using a spear-phishing
              SVT downloader, a common initial access tactic for this group.
              Recommend immediate isolation of the HR department VLAN.&quot;
            </p>
          </div>
          <button className="mt-4 w-full py-3 rounded-[9999px] text-[12px] font-bold uppercase tracking-[1.2px] bg-[#00666d] dark:bg-strix-cyan text-[#cffbff] dark:text-[#0b0e14] hover:opacity-90 transition-opacity">
            Apply Isolation
          </button>
        </div>
      </div>

      {/* Bottom Row: Timeline Events + Live Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Attack Timeline Events */}
        <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-[1.2px]">
              Attack Timeline
            </h3>
            <div className="flex items-center gap-2">
              <span className="text-[10px] px-3 py-1 rounded-[9999px] bg-[#baf1ff] text-[#00666d] dark:bg-strix-cyan/10 dark:text-strix-cyan font-bold uppercase tracking-[0.5px]">
                LATERAL PIVOTS
              </span>
              <span className="text-[10px] px-3 py-1 rounded-[9999px] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] text-[#497f8b] dark:text-[var(--strix-text-muted)] font-bold uppercase tracking-[0.5px]">
                COMPRESSED EVENTS
              </span>
            </div>
          </div>
          <TimelineChart events={timelineEvents} />
        </div>

        {/* Live Feed */}
        <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-[1.2px]">
              Live Feed
            </h3>
            <button className="text-[10px] text-[#00666d] dark:text-strix-cyan font-bold uppercase tracking-[0.5px] hover:underline">
              View all
            </button>
          </div>
          <div className="space-y-0">
            {mockAlerts.slice(0, 3).map((alert) => (
              <LiveAlertCard key={alert.id} alert={alert} compact />
            ))}
          </div>
        </div>
      </div>

      {/* Bottom KPI Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {dashboardKPIs.map((kpi, i) => {
          const Icon = kpiIcons[i]
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
