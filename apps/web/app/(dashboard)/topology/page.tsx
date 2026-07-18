"use client"

// Topology page — trimmed per design pass: the page now hosts only the
// two simulation surfaces (Simulation Topology Panel + GNN Victim Graph).
// The legacy network-graph card, Network Vitals, host detail card, Segment
// Health pill, and bottom status bar were removed; the data those panels
// rendered is still available via the dashboard's other surfaces.

import { SimulationTopologyPanel } from "@/components/topology/simulation-topology-panel"
import { GraphEvolution } from "@/components/charts/graph-evolution"

export default function TopologyPage() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div data-tour="topo-sim" className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6">
          <SimulationTopologyPanel />
        </div>
        <div data-tour="topo-gnn" className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[48px] p-6">
          <GraphEvolution />
        </div>
      </div>
    </div>
  )
}
