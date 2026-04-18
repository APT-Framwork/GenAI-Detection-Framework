// -----------------------------------------------------------------------------
// VictimGraph — interactive force-directed view of infected/connected hosts.
//
// Backed by GET /api/v1/dashboard/victim-graph. Uses reactflow for layout
// and rendering. Auto-polls every 60 s via Tanstack Query (see
// `useVictimGraph`); pauses when the tab is hidden per §12 Q6.
// -----------------------------------------------------------------------------

"use client";

import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  type Edge,
  type Node,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";

import { useVictimGraph, type WindowLiteral } from "@/lib/api/hooks";

interface Props {
  window?: WindowLiteral;
  className?: string;
}

/** Severity → tailwind border colour. */
const SEVERITY_RING: Record<string, string> = {
  critical: "ring-2 ring-red-500",
  high: "ring-2 ring-orange-500",
  medium: "ring-2 ring-yellow-500",
  low: "ring-2 ring-cyan-400",
  info: "ring-2 ring-slate-400",
};

export function VictimGraph({ window = "1h", className = "" }: Props) {
  const { data, isLoading, error } = useVictimGraph(window);

  const { nodes, edges } = useMemo<{ nodes: Node[]; edges: Edge[] }>(() => {
    const apiNodes = data?.nodes ?? [];
    const apiEdges = data?.edges ?? [];
    const radius = 220;
    const cx = 320;
    const cy = 220;
    const total = Math.max(apiNodes.length, 1);
    const nodes: Node[] = apiNodes.map((n, i) => {
      const angle = (i / total) * Math.PI * 2;
      const ring = SEVERITY_RING[n.severity] ?? SEVERITY_RING.info;
      return {
        id: n.hostId,
        position: {
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
        },
        data: {
          label: (
            <div className={`px-3 py-2 rounded-2xl bg-white text-xs font-medium ${ring}`}>
              <div>{n.hostName}</div>
              <div className="text-[10px] text-slate-500">
                risk {(n.riskScore * 100).toFixed(0)}%
              </div>
            </div>
          ),
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });
    const edges: Edge[] = apiEdges.map((e, i) => ({
      id: `${e.from}-${e.to}-${i}`,
      source: e.from,
      target: e.to,
      label: e.edgeType,
      animated: true,
      style: { stroke: "#00666d", strokeWidth: 1.5 },
    }));
    return { nodes, edges };
  }, [data]);

  if (isLoading && !data) {
    return (
      <div className={`flex items-center justify-center h-72 ${className}`}>
        <span className="text-sm text-slate-500">Loading victim graph…</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className={`flex items-center justify-center h-72 ${className}`}>
        <span className="text-sm text-red-500">Failed to load victim graph.</span>
      </div>
    );
  }
  if (!nodes.length) {
    return (
      <div className={`flex items-center justify-center h-72 ${className}`}>
        <span className="text-sm text-slate-500">No connected victims in window.</span>
      </div>
    );
  }

  return (
    <div className={`h-72 w-full ${className}`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesDraggable
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} color="#cffbff" />
        <Controls position="bottom-right" showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
