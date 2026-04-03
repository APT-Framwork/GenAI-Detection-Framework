"use client"

import { cn } from "@/lib/utils"
import {
  RefreshCw,
  Download,
  Plus,
  Minus,
  Maximize2,
  Activity,
  Shield,
  Timer,
  Sparkles,
  Clock,
  Server,
  Database,
  Cloud,
  Monitor,
} from "lucide-react"

/* ── Inline mock data for this Figma-matched layout ─────────── */

const logEntries = [
  { time: "14:22:03", type: "PING", message: "10.0.14.22 SUCCESS", alert: false },
  { time: "14:22:04", type: "INGRESS", message: "4.2 MB encrypted packet", alert: false },
  { time: "14:22:09", type: "ALERT", message: "Unauthorized SSH attempt", alert: true },
  { time: "14:22:12", type: "PROCESS", message: "Kernel-Init ID:4490", alert: false },
  { time: "14:22:15", type: "_", message: "listening for inbound signals...", alert: false },
]

/* ── SVG Network Graph Nodes ───────────────────────────────── */

interface GraphNode {
  id: string
  label: string
  sublabel?: string
  x: number
  y: number
  icon: "server" | "database" | "cloud" | "monitor" | "sentinel"
  compromised?: boolean
  size: "lg" | "md" | "sm"
}

const graphNodes: GraphNode[] = [
  { id: "core", label: "STRIX CORE", x: 120, y: 220, icon: "server", size: "lg" },
  { id: "datalakes", label: "DATA LAKES", x: 380, y: 200, icon: "database", size: "md" },
  { id: "gateway", label: "EXTERNAL GATEWAY", x: 340, y: 60, icon: "cloud", size: "md" },
  { id: "devcluster", label: "DEV CLUSTER", x: 560, y: 320, icon: "monitor", size: "md" },
  { id: "s01", label: "S-01", x: 240, y: 360, icon: "sentinel", size: "sm" },
  { id: "s02", label: "S-02", x: 520, y: 120, icon: "sentinel", size: "sm" },
  { id: "s03", label: "S-03", x: 560, y: 210, icon: "sentinel", size: "sm", compromised: true },
]

interface GraphEdge {
  from: string
  to: string
  compromised?: boolean
}

const graphEdges: GraphEdge[] = [
  { from: "core", to: "datalakes" },
  { from: "core", to: "gateway" },
  { from: "core", to: "s01" },
  { from: "datalakes", to: "devcluster" },
  { from: "datalakes", to: "s03", compromised: true },
  { from: "gateway", to: "s02" },
  { from: "devcluster", to: "s03", compromised: true },
]

function getNodeCenter(node: GraphNode): { cx: number; cy: number } {
  const r = node.size === "lg" ? 44 : node.size === "md" ? 34 : 22
  return { cx: node.x + r, cy: node.y + r }
}

function NodeIcon({ type, size }: { type: GraphNode["icon"]; size: number }) {
  const props = { width: size, height: size, strokeWidth: 1.5 }
  switch (type) {
    case "server": return <Server {...props} />
    case "database": return <Database {...props} />
    case "cloud": return <Cloud {...props} />
    case "monitor": return <Monitor {...props} />
    case "sentinel": return <Shield {...props} />
  }
}

export default function TopologyPage() {
  const nodeMap = Object.fromEntries(graphNodes.map((n) => [n.id, n]))

  return (
    <div className="space-y-6">
      {/* ── Header ────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-[36px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            System Topology
          </h1>
          <p className="text-[14px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-1 max-w-[540px] leading-relaxed">
            Deep-branch visualization of the STRIX core network hierarchy. Inspect real-time data flow between subnets and active sentinels.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <button className="flex items-center gap-2 bg-[#00666d] text-[#cffbff] rounded-[9999px] px-[24px] py-[10px] text-[13px] font-semibold uppercase tracking-wider hover:bg-[#005a60] transition-colors">
            <RefreshCw className="h-4 w-4" />
            Re-Scan Topology
          </button>
          <button className="flex items-center gap-2 rounded-[9999px] px-[24px] py-[10px] text-[13px] font-semibold uppercase tracking-wider border border-[rgba(128,182,195,0.3)] text-[#00343d] dark:text-[var(--strix-text)] dark:border-[var(--strix-border)] hover:bg-[#d6f6ff]/50 dark:hover:bg-[var(--strix-bg-surface)] transition-colors">
            <Download className="h-4 w-4" />
            Export Map
          </button>
        </div>
      </div>

      {/* ── Main Grid ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* ── Left: Network Graph (col 1-8) ───────────────── */}
        <div className="lg:col-span-8 bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6 relative overflow-hidden">
          {/* Zoom Controls */}
          <div className="absolute top-8 left-8 z-10 flex flex-col gap-1">
            {[
              { icon: Plus, label: "Zoom in" },
              { icon: Minus, label: "Zoom out" },
              { icon: Maximize2, label: "Expand" },
            ].map(({ icon: Icon, label }) => (
              <button
                key={label}
                aria-label={label}
                className="w-9 h-9 flex items-center justify-center rounded-[12px] bg-white/80 dark:bg-[var(--strix-bg-surface)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] text-[#00343d] dark:text-[var(--strix-text)] hover:bg-[#d6f6ff] dark:hover:bg-[var(--strix-bg-card)] transition-colors"
              >
                <Icon className="h-4 w-4" />
              </button>
            ))}
          </div>

          {/* SVG Graph */}
          <svg
            viewBox="0 0 700 440"
            className="w-full h-auto"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Background grid pattern */}
            <defs>
              <pattern id="topo-grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" className="stroke-[rgba(128,182,195,0.08)] dark:stroke-[rgba(128,182,195,0.06)]" strokeWidth="0.5" />
              </pattern>
              {/* Glow filter for active nodes */}
              <filter id="teal-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feFlood floodColor="#87edf6" floodOpacity="0.25" />
                <feComposite in2="blur" operator="in" />
                <feMerge>
                  <feMergeNode />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="red-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feFlood floodColor="#b31b25" floodOpacity="0.3" />
                <feComposite in2="blur" operator="in" />
                <feMerge>
                  <feMergeNode />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <rect width="100%" height="100%" fill="url(#topo-grid)" />

            {/* Edges */}
            {graphEdges.map((edge, i) => {
              const fromNode = nodeMap[edge.from]
              const toNode = nodeMap[edge.to]
              if (!fromNode || !toNode) return null
              const from = getNodeCenter(fromNode)
              const to = getNodeCenter(toNode)
              return (
                <line
                  key={i}
                  x1={from.cx}
                  y1={from.cy}
                  x2={to.cx}
                  y2={to.cy}
                  stroke={edge.compromised ? "#b31b25" : "#87edf6"}
                  strokeWidth={edge.compromised ? 2 : 1.5}
                  strokeDasharray={edge.compromised ? "8 4" : "none"}
                  opacity={edge.compromised ? 0.8 : 0.5}
                />
              )
            })}

            {/* Nodes */}
            {graphNodes.map((node) => {
              const r = node.size === "lg" ? 44 : node.size === "md" ? 34 : 22
              const iconSize = node.size === "lg" ? 22 : node.size === "md" ? 18 : 14
              const fontSize = node.size === "sm" ? 9 : 10
              const cx = node.x + r
              const cy = node.y + r

              return (
                <g key={node.id} className="cursor-pointer">
                  {/* Outer ring / bg */}
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r}
                    className={cn(
                      node.compromised
                        ? "fill-[#b31b25]/10 stroke-[#b31b25]"
                        : "fill-[#d6f6ff] dark:fill-[rgba(135,237,246,0.08)] stroke-[#87edf6]"
                    )}
                    strokeWidth={node.compromised ? 2 : 1}
                    filter={node.compromised ? "url(#red-glow)" : node.size === "lg" ? "url(#teal-glow)" : undefined}
                  />
                  {/* Inner circle */}
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r * 0.7}
                    className={cn(
                      node.compromised
                        ? "fill-[#b31b25]/20 stroke-[#b31b25]/40"
                        : "fill-white dark:fill-[var(--strix-bg-card)] stroke-[#87edf6]/30"
                    )}
                    strokeWidth={0.5}
                  />
                  {/* Icon */}
                  <foreignObject
                    x={cx - iconSize / 2}
                    y={cy - iconSize / 2 - (node.size !== "sm" ? 4 : 0)}
                    width={iconSize}
                    height={iconSize}
                  >
                    <div className={cn(
                      "flex items-center justify-center",
                      node.compromised ? "text-[#b31b25]" : "text-[#00666d] dark:text-[#87edf6]"
                    )}>
                      <NodeIcon type={node.icon} size={iconSize} />
                    </div>
                  </foreignObject>
                  {/* Label */}
                  <text
                    x={cx}
                    y={cy + (node.size === "sm" ? 10 : 14)}
                    textAnchor="middle"
                    className={cn(
                      "font-semibold",
                      node.compromised
                        ? "fill-[#b31b25]"
                        : "fill-[#00343d] dark:fill-[var(--strix-text)]"
                    )}
                    fontSize={fontSize}
                    fontFamily="var(--font-space-grotesk), system-ui, sans-serif"
                  >
                    {node.label}
                  </text>
                </g>
              )
            })}
          </svg>

          {/* Segment Health badge */}
          <div className="absolute bottom-8 left-8 flex items-center gap-2 bg-white/90 dark:bg-[var(--strix-bg-surface)]/90 backdrop-blur-sm rounded-[9999px] px-4 py-2 border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
            <div className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider font-medium">Segment Health</span>
            <span className="text-[11px] text-[#00343d] dark:text-[var(--strix-text)] font-bold">OPTIMAL (99.9%)</span>
          </div>
        </div>

        {/* ── Right Column (col 9-12) ─────────────────────── */}
        <div className="lg:col-span-4 flex flex-col gap-5">
          {/* ── Network Vitals Card ─────────────────────────── */}
          <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-[24px]">
            <div className="flex items-center gap-2 mb-1">
              <Activity className="h-4 w-4 text-[#00666d] dark:text-[#87edf6]" />
              <h3 className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-wide font-[family-name:var(--font-space-grotesk)]">
                Network Vitals
              </h3>
            </div>
            <p className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-[0.15em] mb-5">
              Real-Time Throughput Metrics
            </p>

            <div className="space-y-5">
              {/* Traffic Volume */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider font-medium">
                    Traffic Volume
                  </span>
                  <span className="text-[14px] font-bold text-[#00666d] dark:text-[#87edf6]">
                    1.4 GB/S
                  </span>
                </div>
                <div className="h-2 rounded-full bg-[rgba(128,182,195,0.12)] dark:bg-[var(--strix-border)] overflow-hidden">
                  <div className="h-full w-[72%] rounded-full bg-[#00666d] dark:bg-[#87edf6]" />
                </div>
              </div>

              {/* Active Sentinels */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider font-medium">
                    Active Sentinels
                  </span>
                  <span className="text-[14px] font-bold text-[#00666d] dark:text-[#87edf6]">
                    42 / 48
                  </span>
                </div>
                <div className="h-2 rounded-full bg-[rgba(128,182,195,0.12)] dark:bg-[var(--strix-border)] overflow-hidden">
                  <div className="h-full w-[87.5%] rounded-full bg-[#00666d] dark:bg-[#87edf6]" />
                </div>
              </div>

              {/* Threat Pressure */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider font-medium">
                    Threat Pressure
                  </span>
                  <span className="text-[14px] font-bold text-[#b31b25]">
                    Moderate
                  </span>
                </div>
                <div className="h-2 rounded-full bg-[rgba(128,182,195,0.12)] dark:bg-[var(--strix-border)] overflow-hidden">
                  <div className="h-full w-[40%] rounded-full bg-[#b31b25]" />
                </div>
              </div>
            </div>
          </div>

          {/* ── Node Details Card ───────────────────────────── */}
          <div className="bg-[#d6f6ff] dark:bg-[var(--strix-bg-surface)] rounded-[48px] p-[24px] border-l-4 border-l-[#00666d] dark:border-l-[#87edf6] relative overflow-hidden">
            <h3 className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-wide mb-4 font-[family-name:var(--font-space-grotesk)]">
              NODE_B4-22_DEV
            </h3>

            {/* Info Boxes */}
            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className="bg-white/60 dark:bg-[var(--strix-bg-card)]/60 rounded-[16px] px-3 py-2.5">
                <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider block mb-0.5">
                  IP Address
                </span>
                <span className="text-[13px] font-bold text-[#00343d] dark:text-[var(--strix-text)] font-mono">
                  10.0.14.22
                </span>
              </div>
              <div className="bg-white/60 dark:bg-[var(--strix-bg-card)]/60 rounded-[16px] px-3 py-2.5">
                <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider block mb-0.5">
                  Status
                </span>
                <span className="text-[13px] font-bold text-[#b31b25] uppercase">
                  Unsecured
                </span>
              </div>
            </div>

            {/* Live Log Stream */}
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <div className="h-2 w-2 rounded-full bg-[#b31b25] animate-pulse" />
                <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider font-medium">
                  Live Log Stream
                </span>
              </div>
              <div className="bg-[#00343d] dark:bg-[#0a1a1f] rounded-[20px] p-4 space-y-1 font-mono text-[11px] leading-[1.7] overflow-hidden">
                {logEntries.map((entry, i) => (
                  <div
                    key={i}
                    className={cn(
                      entry.alert
                        ? "text-[#ff6b6b]"
                        : entry.type === "_"
                        ? "text-[#497f8b]"
                        : "text-[#87edf6]"
                    )}
                  >
                    <span className="text-[#497f8b]">[{entry.time}]</span>{" "}
                    {entry.type === "_" ? (
                      <span className="italic">_{entry.message}</span>
                    ) : (
                      <>
                        <span className={entry.alert ? "text-[#ff6b6b] font-semibold" : "text-[#9ae9fc]"}>
                          {entry.type}:
                        </span>{" "}
                        {entry.message}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Bottom Status Bar ─────────────────────────────── */}
      <div className="relative">
        <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] px-[24px] py-[16px]">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { icon: Shield, label: "ENCRYPTION STATUS", value: "Quantum-Grade Active" },
              { icon: Timer, label: "NETWORK LATENCY", value: "1.2ms Global Avg" },
              { icon: Sparkles, label: "AI ORCHESTRATION", value: "Autonomous Level 4" },
              { icon: Clock, label: "LAST RE-SCAN", value: "02m 45s ago" },
            ].map(({ icon: Icon, label, value }) => (
              <div key={label} className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-full bg-[#d6f6ff] dark:bg-[rgba(135,237,246,0.08)] flex items-center justify-center shrink-0">
                  <Icon className="h-4 w-4 text-[#00666d] dark:text-[#87edf6]" />
                </div>
                <div className="min-w-0">
                  <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider block">
                    {label}
                  </span>
                  <span className="text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] truncate block">
                    {value}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* FAB Button */}
        <button className="absolute -bottom-3 right-6 h-[48px] w-[48px] bg-[#00666d] hover:bg-[#005a60] text-white rounded-full flex items-center justify-center shadow-lg transition-colors">
          <Plus className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}
