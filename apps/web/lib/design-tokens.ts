// -----------------------------------------------------------------------------
// Design tokens (Phase 3).
//
// Severity palette is the canonical mapping used by every stream-bound panel
// (log feed, topology, GNN graph, kill-chain, detection-quality). Cluster
// palette is for GNN node colouring — stable hash(id) → palette index so a
// given cluster keeps the same colour across rerenders.
// -----------------------------------------------------------------------------

export type Severity = "critical" | "high" | "medium" | "low" | "benign";

export const severityColors: Record<Severity, { fg: string; bg: string; border: string }> = {
  critical: { fg: "#EF4444", bg: "rgba(239,68,68,0.12)", border: "rgba(239,68,68,0.45)" },
  high:     { fg: "#F97316", bg: "rgba(249,115,22,0.12)", border: "rgba(249,115,22,0.45)" },
  medium:   { fg: "#EAB308", bg: "rgba(234,179,8,0.12)",  border: "rgba(234,179,8,0.45)"  },
  low:      { fg: "#22C55E", bg: "rgba(34,197,94,0.12)",  border: "rgba(34,197,94,0.45)"  },
  benign:   { fg: "#3B82F6", bg: "rgba(59,130,246,0.10)", border: "rgba(59,130,246,0.35)" },
};

/** Map a CKC stage (0..7) onto the severity palette. */
export function severityFromCkcStage(stage: number): Severity {
  if (stage >= 6) return "critical";
  if (stage >= 4) return "high";
  if (stage >= 2) return "medium";
  if (stage >= 1) return "low";
  return "benign";
}

/** Map a GNN node_risk in [0,1] onto the severity palette. */
export function severityFromRisk(risk: number): Severity {
  if (risk >= 0.85) return "critical";
  if (risk >= 0.65) return "high";
  if (risk >= 0.40) return "medium";
  if (risk >= 0.10) return "low";
  return "benign";
}

// ---- Cluster palette ---------------------------------------------------------

/**
 * 12-colour qualitative palette tuned for the dark-mode dashboard. Picked to
 * keep adjacent indices visually distinct (no two consecutive entries share a
 * hue family) so the FNV-hash collisions in `clusterColor` don't look noisy.
 */
export const clusterPalette: readonly string[] = [
  "#00F2FF", "#8A2BE2", "#F59E0B", "#22C55E", "#F472B6", "#06B6D4",
  "#EAB308", "#A78BFA", "#EF4444", "#10B981", "#FB923C", "#0EA5E9",
];

/** FNV-1a 32-bit. Pure, stable across runs — no Math.random. */
function fnv1a(input: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h >>> 0;
}

/** Stable colour for a cluster id. */
export function clusterColor(clusterId: string | number | null | undefined): string {
  if (clusterId === null || clusterId === undefined) return clusterPalette[0];
  const key = typeof clusterId === "number" ? String(clusterId) : clusterId;
  return clusterPalette[fnv1a(key) % clusterPalette.length];
}
