"use client"

import { useMemo, useState } from "react"
import { cn } from "@/lib/utils"

interface ApiNode {
  hostId: string
  hostName?: string
  ckcStage?: number
  severity?: string
}
interface ApiEdge {
  from: string
  to: string
  type?: string
}
interface ApiSnapshot {
  ts: string
  nodes: ApiNode[] | Array<Record<string, unknown>>
  edges: ApiEdge[] | Array<Record<string, unknown>>
}

interface GraphEvolutionProps {
  className?: string
  snapshots?: ApiSnapshot[] | unknown
}

const SEV_RING: Record<string, { ring: string; dot: string }> = {
  critical: { ring: "bg-red-500/10 border-red-400/40", dot: "bg-red-500" },
  high: { ring: "bg-orange-500/10 border-orange-400/40", dot: "bg-orange-500" },
  medium: { ring: "bg-yellow-500/10 border-yellow-400/40", dot: "bg-yellow-500" },
  low: { ring: "bg-cyan-500/10 border-cyan-400/40", dot: "bg-cyan-500" },
  info: {
    ring:
      "bg-emerald-500/10 border-emerald-400/40 dark:bg-emerald-500/15 dark:border-emerald-500/30",
    dot: "bg-emerald-500",
  },
}

function severityFor(stage: number | undefined, fallback: string | undefined): string {
  if (fallback && fallback in SEV_RING) return fallback
  const s = Number(stage ?? 0)
  if (s >= 7) return "critical"
  if (s >= 5) return "high"
  if (s >= 3) return "medium"
  if (s >= 1) return "low"
  return "info"
}

function isApiNode(v: unknown): v is ApiNode {
  return typeof v === "object" && v !== null && "hostId" in (v as Record<string, unknown>)
}
function isApiEdge(v: unknown): v is ApiEdge {
  return (
    typeof v === "object" &&
    v !== null &&
    "from" in (v as Record<string, unknown>) &&
    "to" in (v as Record<string, unknown>)
  )
}

export function GraphEvolution({ className, snapshots }: GraphEvolutionProps) {
  const [activeTab, setActiveTab] = useState<"nodes" | "edges">("nodes")

  const list = Array.isArray(snapshots) ? (snapshots as ApiSnapshot[]) : []

  // We render the latest non-empty snapshot — that's the one that best
  // captures the chain's connectivity. A future iteration can add a
  // play/pause animation across snapshots[].
  const latest = useMemo(() => {
    for (let i = list.length - 1; i >= 0; i--) {
      const s = list[i]
      if (s && Array.isArray(s.nodes) && s.nodes.length > 0) return s
    }
    return null
  }, [list])

  const nodes: ApiNode[] = useMemo(
    () => ((latest?.nodes ?? []) as unknown[]).filter(isApiNode),
    [latest],
  )
  const edges: ApiEdge[] = useMemo(
    () => ((latest?.edges ?? []) as unknown[]).filter(isApiEdge),
    [latest],
  )

  // Lay nodes out on a circle. Stable across re-renders.
  const positioned = useMemo(() => {
    const cx = 320
    const cy = 160
    const r = 110
    const n = Math.max(nodes.length, 1)
    return nodes.map((node, i) => {
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2
      return {
        ...node,
        x: cx + Math.cos(angle) * r - 60,
        y: cy + Math.sin(angle) * r - 22,
      }
    })
  }, [nodes])

  const nodeById = useMemo(() => {
    const m = new Map<string, (typeof positioned)[number]>()
    positioned.forEach((p) => m.set(p.hostId, p))
    return m
  }, [positioned])

  return (
    <div className={cn("w-full", className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
          Graph Evolution Timeline
        </h3>
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab("nodes")}
            className={cn(
              "px-4 py-1.5 rounded-[9999px] text-[10px] font-semibold uppercase tracking-wider transition-colors",
              activeTab === "nodes"
                ? "bg-[#00666d] text-white dark:bg-[#00666d]"
                : "text-[#497f8b] dark:text-[var(--strix-text-muted)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] hover:bg-gray-50 dark:hover:bg-gray-800"
            )}
          >
            Nodes ({nodes.length})
          </button>
          <button
            onClick={() => setActiveTab("edges")}
            className={cn(
              "px-4 py-1.5 rounded-[9999px] text-[10px] font-semibold uppercase tracking-wider transition-colors",
              activeTab === "edges"
                ? "bg-[#00666d] text-white dark:bg-[#00666d]"
                : "text-[#497f8b] dark:text-[var(--strix-text-muted)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] hover:bg-gray-50 dark:hover:bg-gray-800"
            )}
          >
            Edges ({edges.length})
          </button>
        </div>
      </div>

      {/* Graph area */}
      <div className="relative w-full h-[320px] bg-[#e7faff]/50 dark:bg-[var(--strix-bg-surface)] rounded-[32px] overflow-hidden border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
        {/* Grid pattern */}
        <svg className="absolute inset-0 w-full h-full opacity-15">
          <defs>
            <pattern
              id="graph-grid"
              width="32"
              height="32"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 32 0 L 0 0 0 32"
                fill="none"
                stroke="#497f8b"
                strokeWidth="0.5"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#graph-grid)" />
        </svg>

        {/* Empty state */}
        {nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            No graph data for this chain in window.
          </div>
        )}

        {/* Edges */}
        {edges.length > 0 && (
          <svg className="absolute inset-0 w-full h-full">
            {edges.map((edge, i) => {
              const a = nodeById.get(edge.from)
              const b = nodeById.get(edge.to)
              if (!a || !b) return null
              const malicious = edge.type !== "normal"
              return (
                <line
                  key={`${edge.from}-${edge.to}-${i}`}
                  x1={a.x + 60}
                  y1={a.y + 22}
                  x2={b.x + 60}
                  y2={b.y + 22}
                  stroke={malicious ? "#b31b25" : "rgba(128,182,195,0.55)"}
                  strokeWidth={malicious ? 2 : 1.5}
                  strokeDasharray={malicious ? "8 4" : "none"}
                  opacity={0.65}
                />
              )
            })}
          </svg>
        )}

        {/* Nodes */}
        {positioned.map((node) => {
          const sev = severityFor(node.ckcStage, node.severity)
          const styles = SEV_RING[sev] ?? SEV_RING.info
          const label = node.hostName ?? node.hostId
          const sublabel =
            node.ckcStage != null ? `stage ${node.ckcStage}` : sev.toUpperCase()
          return (
            <div
              key={node.hostId}
              className="absolute"
              style={{ left: node.x, top: node.y }}
            >
              <div
                className={cn(
                  "px-4 py-2.5 rounded-2xl border text-center min-w-[120px] backdrop-blur-sm",
                  styles.ring,
                )}
              >
                <div className="flex items-center gap-2 justify-center">
                  <div className={cn("h-2.5 w-2.5 rounded-full", styles.dot)} />
                  <span className="text-[11px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                    {label}
                  </span>
                </div>
                <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] block mt-1">
                  {sublabel}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
