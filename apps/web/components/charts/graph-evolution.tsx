"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"

interface GraphNode {
  id: string
  label: string
  sublabel: string
  x: number
  y: number
  color: string
  dotColor: string
}

interface GraphEdge {
  from: string
  to: string
  type: "normal" | "malicious"
}

const nodes: GraphNode[] = [
  {
    id: "n1",
    label: "WEB-SRV-01",
    sublabel: "Inbound Port 443",
    x: 80,
    y: 60,
    color: "bg-red-500/10 border-red-400/40 dark:bg-red-500/15 dark:border-red-500/30",
    dotColor: "bg-red-500",
  },
  {
    id: "n2",
    label: "SQL-CLUSTER",
    sublabel: "Lateral Movement Target",
    x: 280,
    y: 180,
    color:
      "bg-emerald-500/10 border-emerald-400/40 dark:bg-emerald-500/15 dark:border-emerald-500/30",
    dotColor: "bg-emerald-500",
  },
  {
    id: "n3",
    label: "ADMIN-WS-09",
    sublabel: "Impersonated Token",
    x: 120,
    y: 250,
    color:
      "bg-blue-500/10 border-blue-400/40 dark:bg-blue-500/15 dark:border-blue-500/30",
    dotColor: "bg-[#005ea0]",
  },
]

const edges: GraphEdge[] = [
  { from: "n1", to: "n2", type: "malicious" },
  { from: "n3", to: "n2", type: "malicious" },
  { from: "n1", to: "n3", type: "normal" },
]

interface GraphEvolutionProps {
  className?: string
}

export function GraphEvolution({ className }: GraphEvolutionProps) {
  const [activeTab, setActiveTab] = useState<"nodes" | "edges">("nodes")
  const getNodePos = (id: string) => nodes.find((n) => n.id === id)

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
            Nodes
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
            Edges
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

        {/* Edges */}
        <svg className="absolute inset-0 w-full h-full">
          {edges.map((edge, i) => {
            const from = getNodePos(edge.from)
            const to = getNodePos(edge.to)
            if (!from || !to) return null
            return (
              <line
                key={i}
                x1={from.x + 60}
                y1={from.y + 22}
                x2={to.x + 60}
                y2={to.y + 22}
                stroke={
                  edge.type === "malicious"
                    ? "#b31b25"
                    : "rgba(128,182,195,0.4)"
                }
                strokeWidth={edge.type === "malicious" ? 2 : 1.5}
                strokeDasharray={edge.type === "malicious" ? "8 4" : "none"}
                opacity={0.6}
              />
            )
          })}
        </svg>

        {/* Nodes */}
        {nodes.map((node) => (
          <div
            key={node.id}
            className="absolute"
            style={{ left: node.x, top: node.y }}
          >
            <div
              className={cn(
                "px-4 py-2.5 rounded-2xl border text-center min-w-[120px] backdrop-blur-sm",
                node.color
              )}
            >
              <div className="flex items-center gap-2 justify-center">
                <div className={cn("h-2.5 w-2.5 rounded-full", node.dotColor)} />
                <span className="text-[11px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                  {node.label}
                </span>
              </div>
              <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] block mt-1">
                {node.sublabel}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
