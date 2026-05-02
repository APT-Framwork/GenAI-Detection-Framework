"use client"

import { useMemo, useState } from "react"
import { cn } from "@/lib/utils"
import { useTopology } from "@/lib/api/topology"
import { useLiveFeed } from "@/lib/api/live-feed"
import { downloadJson } from "@/lib/download"
import { toast } from "@/lib/toast"
import {
  RefreshCw,
  Download,
  Activity,
  Shield,
  Timer,
  Sparkles,
  Clock,
  Server,
  Database,
  Cloud,
  Monitor,
  Loader2,
} from "lucide-react"

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

// graphNodes are derived from the topology API at render time — see
// useTopology() in TopologyPage. The constant below is the empty fallback.
const graphNodes: GraphNode[] = []

interface GraphEdge {
  from: string
  to: string
  compromised?: boolean
}

// see TopologyPage for the derived list.
const graphEdges: GraphEdge[] = []

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
  const topology = useTopology("24h")
  const liveFeed = useLiveFeed({ maxEvents: 200 })
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  // Derive SVG GraphNode/GraphEdge from the API. Lay nodes out on a circle
  // around the canvas centre — deterministic, no dependence on a layout lib.
  const { nodes, edges, nodeMap } = useMemo(() => {
    const apiNodes = topology.data?.nodes ?? []
    const apiEdges = topology.data?.edges ?? []
    const cx = 350
    const cy = 220
    const r = Math.max(120, Math.min(180, 30 * apiNodes.length))
    const layoutNodes: GraphNode[] = apiNodes.map((n, i) => {
      const t = (i / Math.max(apiNodes.length, 1)) * Math.PI * 2
      const ix = n.type === "manager" ? "server" : n.type === "database" ? "database" : "monitor"
      return {
        id: n.id,
        label: n.label,
        sublabel: n.ip ?? undefined,
        x: cx + Math.cos(t) * r - 34,
        y: cy + Math.sin(t) * r - 34,
        icon: ix,
        compromised: n.status === "compromised",
        size: n.type === "manager" ? "lg" : "md",
      }
    })
    const layoutEdges: GraphEdge[] = apiEdges.map((e) => ({
      from: e.source, to: e.target, compromised: e.type === "malicious",
    }))
    return {
      nodes: layoutNodes,
      edges: layoutEdges,
      nodeMap: Object.fromEntries(layoutNodes.map((n) => [n.id, n])),
    }
  }, [topology.data])

  // Real selected-node detail. If nothing's clicked, show the first
  // compromised host (or the first host overall).
  const apiNodes = topology.data?.nodes ?? []
  const selectedNode = useMemo(() => {
    if (selectedNodeId) {
      return apiNodes.find((n) => n.id === selectedNodeId) ?? null
    }
    const compromised = apiNodes.find((n) => n.status === "compromised")
    return compromised ?? apiNodes[0] ?? null
  }, [apiNodes, selectedNodeId])

  // Real network vitals derived from the topology + live feed.
  const totalHosts = apiNodes.length
  const healthyHosts = apiNodes.filter((n) => n.status === "healthy").length
  const compromisedHosts = apiNodes.filter((n) => n.status === "compromised").length
  const trafficPerMin = useMemo(() => {
    const cutoff = Date.now() - 60_000
    return liveFeed.events.filter((e) => {
      const t = Date.parse(e.data.occurredAt)
      return Number.isFinite(t) && t >= cutoff
    }).length
  }, [liveFeed.events])
  const threatPressure: { label: string; pct: number; color: string } = useMemo(() => {
    if (totalHosts === 0) return { label: "Idle", pct: 0, color: "#497f8b" }
    const ratio = compromisedHosts / totalHosts
    if (ratio === 0) return { label: "Low", pct: 8, color: "#10B981" }
    if (ratio < 0.2) return { label: "Moderate", pct: 40, color: "#F59E0B" }
    if (ratio < 0.5) return { label: "Elevated", pct: 70, color: "#EA580C" }
    return { label: "Critical", pct: 95, color: "#b31b25" }
  }, [totalHosts, compromisedHosts])
  const segmentHealthPct = totalHosts === 0 ? 100 : Math.round((healthyHosts / totalHosts) * 1000) / 10
  const segmentHealthLabel = segmentHealthPct >= 95 ? "OPTIMAL" : segmentHealthPct >= 80 ? "DEGRADED" : "CRITICAL"

  // "Last re-scan" — when the topology query last returned. Formatted
  // as relative time, refreshes when query refetches.
  const lastRescanLabel = useMemo(() => {
    const t = topology.dataUpdatedAt
    if (!t) return "—"
    const secs = Math.max(0, Math.round((Date.now() - t) / 1000))
    if (secs < 60) return `${secs}s ago`
    if (secs < 3600) return `${Math.floor(secs / 60)}m ${String(secs % 60).padStart(2, "0")}s ago`
    return `${Math.floor(secs / 3600)}h ago`
  // include `liveFeed.events.length` so the label re-renders periodically
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topology.dataUpdatedAt, liveFeed.events.length])

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
          <button
            onClick={() => {
              topology.refetch()
              toast.info("Re-scanning topology…")
            }}
            disabled={topology.isFetching}
            className="flex items-center gap-2 bg-[#00666d] text-[#cffbff] rounded-[9999px] px-[24px] py-[10px] text-[13px] font-semibold uppercase tracking-wider hover:bg-[#005a60] transition-colors disabled:opacity-60"
          >
            <RefreshCw className={cn("h-4 w-4", topology.isFetching && "animate-spin")} />
            Re-Scan Topology
          </button>
          <button
            onClick={() => {
              if (!topology.data) {
                toast.warning("No topology data to export yet.")
                return
              }
              const stamp = new Date().toISOString().replace(/[:.]/g, "-")
              downloadJson(`strix-topology-${stamp}.json`, topology.data)
              toast.success("Topology snapshot exported.")
            }}
            className="flex items-center gap-2 rounded-[9999px] px-[24px] py-[10px] text-[13px] font-semibold uppercase tracking-wider border border-[rgba(128,182,195,0.3)] text-[#00343d] dark:text-[var(--strix-text)] dark:border-[var(--strix-border)] hover:bg-[#d6f6ff]/50 dark:hover:bg-[var(--strix-bg-surface)] transition-colors"
          >
            <Download className="h-4 w-4" />
            Export Map
          </button>
        </div>
      </div>

      {/* ── Main Grid ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* ── Left: Network Graph (col 1-8) ───────────────── */}
        <div className="lg:col-span-8 bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6 relative overflow-hidden">
          {/* Hint label — replaces the previous dead zoom controls. */}
          <div className="absolute top-8 left-8 z-10 px-3 py-1.5 rounded-full bg-white/80 dark:bg-[var(--strix-bg-surface)]/80 backdrop-blur border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider font-medium">
            click a node for details · {totalHosts} hosts
          </div>
          {topology.isLoading && !topology.data && (
            <div className="absolute inset-0 flex items-center justify-center z-20 bg-white/70 dark:bg-[var(--strix-bg-card)]/70 backdrop-blur-sm">
              <Loader2 className="h-5 w-5 animate-spin text-[#00666d] dark:text-[#87edf6]" />
            </div>
          )}
          {!topology.isLoading && totalHosts === 0 && (
            <div className="absolute inset-0 flex items-center justify-center z-10 text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] italic">
              No topology yet — start a simulation or wait for the first agent check-in.
            </div>
          )}

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
            {edges.map((edge, i) => {
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
            {nodes.map((node) => {
              const r = node.size === "lg" ? 44 : node.size === "md" ? 34 : 22
              const iconSize = node.size === "lg" ? 22 : node.size === "md" ? 18 : 14
              const fontSize = node.size === "sm" ? 9 : 10
              const cx = node.x + r
              const cy = node.y + r

              return (
                <g
                  key={node.id}
                  className="cursor-pointer"
                  onClick={() => setSelectedNodeId(node.id)}
                >
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

          {/* Segment Health badge — derived from healthy / total hosts. */}
          {totalHosts > 0 && (
            <div className="absolute bottom-8 left-8 flex items-center gap-2 bg-white/90 dark:bg-[var(--strix-bg-surface)]/90 backdrop-blur-sm rounded-[9999px] px-4 py-2 border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
              <div className={cn(
                "h-2.5 w-2.5 rounded-full animate-pulse",
                segmentHealthLabel === "OPTIMAL" ? "bg-emerald-500" : segmentHealthLabel === "DEGRADED" ? "bg-amber-500" : "bg-rose-500",
              )} />
              <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider font-medium">Segment Health</span>
              <span className="text-[11px] text-[#00343d] dark:text-[var(--strix-text)] font-bold">
                {segmentHealthLabel} ({segmentHealthPct.toFixed(1)}%)
              </span>
            </div>
          )}
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
              {/* Traffic — events/min over the SSE feed. */}
              <Vital
                label="Traffic"
                value={`${trafficPerMin}/min`}
                pct={Math.min(100, trafficPerMin * 2)}
                color="#00666d"
              />

              {/* Active Sentinels — healthy hosts vs total. */}
              <Vital
                label="Active Sentinels"
                value={totalHosts > 0 ? `${healthyHosts} / ${totalHosts}` : "—"}
                pct={totalHosts === 0 ? 0 : (healthyHosts / totalHosts) * 100}
                color="#00666d"
              />

              {/* Threat Pressure — derived from compromised count. */}
              <Vital
                label="Threat Pressure"
                value={threatPressure.label}
                pct={threatPressure.pct}
                color={threatPressure.color}
              />
            </div>
          </div>

          {/* ── Node Details Card — driven by selectedNode. */}
          <div className={cn(
            "bg-[#d6f6ff] dark:bg-[var(--strix-bg-surface)] rounded-[48px] p-[24px] border-l-4 relative overflow-hidden",
            selectedNode?.status === "compromised"
              ? "border-l-[#b31b25]"
              : selectedNode?.status === "warning"
              ? "border-l-amber-500"
              : "border-l-[#00666d] dark:border-l-[#87edf6]",
          )}>
            {!selectedNode ? (
              <p className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] italic">
                Click a node in the graph to see its details.
              </p>
            ) : (
              <>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <h3 className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)] uppercase tracking-wide font-[family-name:var(--font-space-grotesk)] truncate">
                    {selectedNode.label}
                  </h3>
                  {selectedNodeId && (
                    <button
                      onClick={() => setSelectedNodeId(null)}
                      className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:underline shrink-0"
                    >
                      clear
                    </button>
                  )}
                </div>
                <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] font-mono mb-4">
                  id {selectedNode.id.length > 18 ? selectedNode.id.slice(0, 18) + "…" : selectedNode.id}
                </p>

                <div className="grid grid-cols-2 gap-3 mb-3">
                  <Info label="IP Address" value={selectedNode.ip ?? "—"} mono />
                  <Info
                    label="Status"
                    value={selectedNode.status.toUpperCase()}
                    valueClass={
                      selectedNode.status === "compromised"
                        ? "text-[#b31b25]"
                        : selectedNode.status === "warning"
                        ? "text-amber-600 dark:text-amber-400"
                        : "text-emerald-600 dark:text-emerald-400"
                    }
                  />
                  <Info label="Type" value={selectedNode.type} />
                  <Info
                    label="Open Chains"
                    value={String(selectedNode.openChains)}
                    valueClass={selectedNode.openChains > 0 ? "text-amber-600 dark:text-amber-400" : ""}
                  />
                </div>

                {selectedNode.maxCkcStage > 0 && (
                  <div className="bg-white/60 dark:bg-[var(--strix-bg-card)]/60 rounded-[16px] px-3 py-2.5 mb-3">
                    <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider block mb-0.5">
                      Max CKC Stage Observed (24 h)
                    </span>
                    <span className="text-[13px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                      {selectedNode.maxCkcStage} / 7
                    </span>
                  </div>
                )}

                <a
                  href={`/threat-intel?q=${encodeURIComponent(selectedNode.label)}`}
                  className="inline-block text-[11px] text-[#00666d] dark:text-[#87edf6] hover:underline font-semibold"
                >
                  Investigate in Threat Intel →
                </a>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Bottom Status Bar — values derived from real signals. */}
      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] px-[24px] py-[16px]">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatusItem
            icon={Shield}
            label="Transport"
            value="HTTPS · WSS"
          />
          <StatusItem
            icon={Timer}
            label="Live Feed"
            value={liveFeed.status}
          />
          <StatusItem
            icon={Sparkles}
            label="DQN Policy"
            value="active · gated"
          />
          <StatusItem
            icon={Clock}
            label="Last Re-Scan"
            value={lastRescanLabel}
          />
        </div>
      </div>
    </div>
  )
}

function Vital({ label, value, pct, color }: { label: string; value: string; pct: number; color: string }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider font-medium">
          {label}
        </span>
        <span className="text-[14px] font-bold" style={{ color }}>
          {value}
        </span>
      </div>
      <div className="h-2 rounded-full bg-[rgba(128,182,195,0.12)] dark:bg-[var(--strix-border)] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }}
        />
      </div>
    </div>
  )
}

function Info({ label, value, mono = false, valueClass = "" }: { label: string; value: string; mono?: boolean; valueClass?: string }) {
  return (
    <div className="bg-white/60 dark:bg-[var(--strix-bg-card)]/60 rounded-[16px] px-3 py-2.5">
      <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider block mb-0.5">
        {label}
      </span>
      <span className={cn("text-[13px] font-bold text-[#00343d] dark:text-[var(--strix-text)]", mono && "font-mono", valueClass)}>
        {value}
      </span>
    </div>
  )
}

function StatusItem({ icon: Icon, label, value }: { icon: typeof Shield; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3">
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
  )
}
