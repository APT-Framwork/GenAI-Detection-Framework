"use client"

import { killChainStages, mockPredictions, forensicLogs } from "@/lib/mock-data"
import { KillChainProgression } from "@/components/charts/kill-chain-progression"
import { GraphEvolution } from "@/components/charts/graph-evolution"
import { AIPredictionsPanel } from "@/components/charts/ai-predictions-panel"
import { ForensicLogViewer } from "@/components/charts/forensic-log-viewer"
import {
  Clock,
  AlertTriangle,
  Download,
  Shield,
  Users,
  HardDrive,
  TrendingUp,
  FileText,
  Zap,
} from "lucide-react"

export default function AttackAnalysisDetailPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] text-strix-primary dark:text-strix-cyan uppercase tracking-widest font-semibold mb-1">
            FORENSIC INCIDENT REPORT
          </p>
          <h1 className="text-3xl font-black text-[var(--strix-text)] tracking-tight">
            External Pivot<br />
            Escalation Analysis
          </h1>
        </div>
        <div className="flex items-center gap-4">
          {/* Severity Badge */}
          <div className="text-right">
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
              Threat Level
            </span>
            <span className="inline-block px-3 py-1 rounded-md text-xs font-bold bg-red-500/10 text-red-500 border border-red-500/20 uppercase">
              Critical
            </span>
          </div>
          {/* Duration */}
          <div className="text-right">
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
              Duration
            </span>
            <div className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
              <span className="text-lg font-bold text-[var(--strix-text)]">
                14m 22s
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Kill Chain Progression */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-6">
        <KillChainProgression stages={killChainStages} />
      </div>

      {/* Graph Evolution + AI Predictions */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Graph Evolution */}
        <div className="lg:col-span-7 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <GraphEvolution />
        </div>

        {/* AI Predictions */}
        <div className="lg:col-span-5 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <AIPredictionsPanel predictions={mockPredictions} />
        </div>
      </div>

      {/* Forensic Logs */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
        <ForensicLogViewer logs={forensicLogs} />
      </div>

      {/* Bottom Metrics Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
            Infection Radius
          </span>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold text-[var(--strix-text)]">12.4%</span>
            <span className="text-xs text-red-500 font-medium">+2.1%</span>
          </div>
          <span className="text-[10px] text-[var(--strix-text-muted)]">Today</span>
        </div>

        <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
            Dwell Time
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-[var(--strix-text)]">04h 22m</span>
          </div>
          <span className="text-[10px] text-[var(--strix-text-muted)]">
            Active · Industry Avg
          </span>
        </div>

        <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
            Data Potential Loss
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-[var(--strix-text)]">2.8 GB</span>
          </div>
          <span className="text-[10px] text-[var(--strix-text-muted)]">
            Encrypted & Staged
          </span>
        </div>

        <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
            Confidence Score
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-[var(--strix-text)]">High</span>
          </div>
          <span className="text-[10px] text-[var(--strix-text-muted)]">
            Model 0.2 · STRIX
          </span>
        </div>
      </div>

      {/* Action Bar */}
      <div className="flex items-center justify-between bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl px-6 py-3">
        <div className="flex items-center gap-3">
          <Users className="h-4 w-4 text-[var(--strix-text-muted)]" />
          <span className="text-xs text-[var(--strix-text-muted)]">
            Collaborating on this case: <span className="font-semibold text-[var(--strix-text)]">Sentinel Ops Team</span>
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
