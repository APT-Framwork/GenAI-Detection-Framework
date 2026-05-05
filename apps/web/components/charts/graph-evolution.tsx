// -----------------------------------------------------------------------------
// graph-evolution.tsx — GNN victim graph (Phase 6).
//
// Two modes:
//   * Live mode (no `snapshots` prop): subscribes to the `gnn` ws stream from
//     `apps/web/lib/api/ws.ts`. Maintains a per-host accumulator that drives an
//     SVG with attacker hub + radial victim nodes. Node radius scales with
//     `node_risk`, fill colour comes from a stable cluster-id hash, edge
//     thickness/colour come from `affected_edges` and the GNN 0.7743 threshold
//     respectively. All transitions are 300 ms.
//   * Legacy mode (`snapshots` prop): used by `/attack-analysis/[id]` — renders
//     the latest non-empty snapshot from the analysis API exactly as before.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useLogStream, type GnnPayload } from "@/lib/api/ws";
import { useLatestSimulationRun } from "@/lib/api/simulation";
import { clusterColor, severityFromRisk, severityColors } from "@/lib/design-tokens";
import { useHostAgentMap } from "@/lib/host-agent-map";

// ---- Shared types -----------------------------------------------------------

interface ApiNode {
  hostId: string;
  hostName?: string;
  ckcStage?: number;
  severity?: string;
}
interface ApiEdge {
  from: string;
  to: string;
  type?: string;
}
interface ApiSnapshot {
  ts: string;
  nodes: ApiNode[] | Array<Record<string, unknown>>;
  edges: ApiEdge[] | Array<Record<string, unknown>>;
}

interface GraphEvolutionProps {
  className?: string;
  snapshots?: ApiSnapshot[] | unknown;
}

export function GraphEvolution(props: GraphEvolutionProps) {
  if (props.snapshots !== undefined) {
    return <LegacyGraphEvolution className={props.className} snapshots={props.snapshots} />;
  }
  return <LiveGraphEvolution className={props.className} />;
}

// ---- Live mode --------------------------------------------------------------

const VIEW_W = 640;
const VIEW_H = 360;
const CENTER_X = 220;
const CENTER_Y = VIEW_H / 2;
const RING_R = 110;
// Top/bottom safe-zone — keep nodes' halos clear of the rounded card corners.
const ANGLE_HALF_RANGE = (Math.PI / 180) * 65; // ±65° instead of ±90°
const HISTORY_CAP = 24;
const MAX_NODES = 14;
const GNN_THRESHOLD = 0.7743;

interface NodeState {
  hostId: string;
  nodeRisk: number;
  neighborRisk: number;
  riskGrowth: number;
  affectedEdges: number;
  srcip: string | null;
  riskHistory: number[];
  lastSeen: number;
}

function pickHostId(p: GnnPayload): string | null {
  const id =
    (typeof p.host_id === "string" && p.host_id) ||
    (typeof p.agent_id === "string" && p.agent_id) ||
    (typeof p.srcip === "string" && p.srcip) ||
    null;
  return id;
}

function LiveGraphEvolution({ className }: { className?: string }) {
  const stream = useLogStream(["gnn"]);
  const seq = stream.seq.gnn;
  // agent_id → hostname mapping learned from raw_log frames in the
  // topology panel. Used to label GNN nodes with their hostname so the
  // graph and topology panel use the same names.
  const { agentToHost } = useHostAgentMap();
  // Topology — seed empty placeholder nodes for every known victim so the
  // panel shows all hosts at idle (radius 8, risk 0) before their first
  // GNN frame arrives. Without this, hosts that haven't fired any alerts
  // yet are invisible and the panel looks half-empty mid-simulation.
  const latestRun = useLatestSimulationRun();
  const victims = latestRun.data?.topology?.victims;

  const nodesRef = useRef<Map<string, NodeState>>(new Map());
  const lastSeqRef = useRef(0);
  const [, setTick] = useState(0);
  const [hoverId, setHoverId] = useState<string | null>(null);

  // Seed placeholder nodes from topology — but ONLY when the topology
  // entry already carries the same identifier the live GNN frames use
  // (`agent_id`). The runtime keys GNN frames by Wazuh agent_id (e.g.
  // "007", "008"), while topology.json typically only has hostnames
  // (e.g. "victim1", "victim2"). Seeding by hostname creates phantom
  // duplicates: the panel ends up showing one placeholder per hostname
  // PLUS one real node per agent_id, doubling the host count.
  // Without an agent_id we can't dedupe → just don't seed.
  useEffect(() => {
    if (!victims || victims.length === 0) return;
    const map = nodesRef.current;
    let dirty = false;
    for (const v of victims) {
      const id = (v.agent_id ?? null) as string | null;
      if (!id) continue; // no agent_id → can't safely dedupe against live frames
      if (!map.has(id)) {
        map.set(id, {
          hostId: id,
          nodeRisk: 0,
          neighborRisk: 0,
          riskGrowth: 0,
          affectedEdges: 0,
          srcip: v.ip ?? null,
          riskHistory: [],
          lastSeen: 0,
        });
        dirty = true;
      }
    }
    if (dirty) setTick((n) => n + 1);
  }, [victims]);

  // Drain new frames into the per-host accumulator. Use a seq watermark so we
  // count each event exactly once even when the ring buffer is shared with
  // other consumers.
  useEffect(() => {
    if (seq <= lastSeqRef.current) return;
    const buf = stream.frames.gnn;
    const fresh = buf.slice(buf.length - (seq - lastSeqRef.current));
    lastSeqRef.current = seq;

    const map = nodesRef.current;
    const now = Date.now();
    for (const env of fresh) {
      const p = env.payload;
      const id = pickHostId(p);
      if (!id) continue;
      const existing = map.get(id);
      const risk = typeof p.node_risk === "number" ? p.node_risk : (existing?.nodeRisk ?? 0);
      const history = existing ? existing.riskHistory.slice() : [];
      history.push(risk);
      if (history.length > HISTORY_CAP) history.splice(0, history.length - HISTORY_CAP);
      map.set(id, {
        hostId: id,
        nodeRisk: risk,
        neighborRisk: typeof p.neighbor_risk === "number" ? p.neighbor_risk : (existing?.neighborRisk ?? 0),
        riskGrowth: typeof p.risk_growth === "number" ? p.risk_growth : (existing?.riskGrowth ?? 0),
        affectedEdges: typeof p.affected_edges === "number" ? p.affected_edges : (existing?.affectedEdges ?? 0),
        srcip: (typeof p.srcip === "string" ? p.srcip : existing?.srcip) ?? null,
        riskHistory: history,
        lastSeen: now,
      });
    }
    setTick((n) => n + 1);
  }, [seq, stream.frames.gnn]);

  // Recency-bounded set of nodes to display. Sorted by hostId for *position*
  // stability (a new host slots into its alphabetical position rather than
  // reshuffling everything).
  const visible = useMemo(() => {
    const all = Array.from(nodesRef.current.values());
    const top = all
      .slice()
      .sort((a, b) => b.lastSeen - a.lastSeen)
      .slice(0, MAX_NODES);
    return top.slice().sort((a, b) => a.hostId.localeCompare(b.hostId));
    // The closure captures `nodesRef.current` mutations via the tick state
    // change above; including the `seq` dep is enough to re-derive.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seq]);

  const positioned = useMemo(() => {
    const n = Math.max(visible.length, 1);
    return visible.map((node, i) => {
      // Spread on a tight arc to the right of the attacker hub. Angular
      // range deliberately less than ±90° so node halos stay clear of the
      // rounded card corners (top node 007 was being clipped at ±π/2).
      const t = n === 1 ? 0.5 : i / (n - 1);
      const a = -ANGLE_HALF_RANGE + t * (2 * ANGLE_HALF_RANGE);
      return {
        ...node,
        x: CENTER_X + Math.cos(a) * RING_R + 80,
        y: CENTER_Y + Math.sin(a) * RING_R,
      };
    });
  }, [visible]);

  const maxRisk = visible.reduce((m, n) => Math.max(m, n.nodeRisk), 0);
  const overallSeverity = severityFromRisk(maxRisk);
  const overallColors = severityColors[overallSeverity];

  // Cluster legend — unique colours present in the visible set.
  const clusters = useMemo(() => {
    const seen = new Map<string, { color: string; count: number }>();
    for (const n of visible) {
      const c = clusterColor(n.hostId);
      const e = seen.get(c);
      if (e) e.count += 1;
      else seen.set(c, { color: c, count: 1 });
    }
    return Array.from(seen.values()).slice(0, 6);
  }, [visible]);

  const hovered = hoverId ? positioned.find((n) => n.hostId === hoverId) : null;

  return (
    <div className={cn("w-full", className)}>
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
          GNN Victim Graph
        </h3>
        <div className="flex items-center gap-3">
          <span
            className="px-3 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider border"
            style={{
              color: overallColors.fg,
              background: overallColors.bg,
              borderColor: overallColors.border,
            }}
          >
            {visible.length} host{visible.length === 1 ? "" : "s"} · max risk {maxRisk.toFixed(2)}
          </span>
          <ConfidenceGauge value={maxRisk} />
        </div>
      </div>

      {/*
        Outer wrapper is `relative` so the tooltip can position against it,
        but it does NOT clip — `overflow-hidden` is pushed down to the inner
        graph shell so the rounded card still masks SVG bleed while the
        tooltip is free to extend past the card boundary when a node is
        near the top edge.
      */}
      <div className="relative w-full">
        <div className="bg-[#e7faff]/50 dark:bg-[var(--strix-bg-surface)] rounded-[32px] overflow-hidden border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
        <svg
          className="w-full block"
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <pattern id="gnn-grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#497f8b" strokeWidth="0.4" />
            </pattern>
            <radialGradient id="atk-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#EF4444" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#EF4444" stopOpacity="0" />
            </radialGradient>
          </defs>

          <rect width={VIEW_W} height={VIEW_H} fill="url(#gnn-grid)" opacity={0.18} />

          {/* Edges from attacker hub to each node */}
          {positioned.map((node) => {
            const malicious = node.nodeRisk >= GNN_THRESHOLD;
            const stroke = malicious ? "#EF4444" : "rgba(128,182,195,0.55)";
            const width = 1 + Math.min(node.affectedEdges, 10) * 0.4;
            return (
              <line
                key={`e-${node.hostId}`}
                x1={CENTER_X}
                y1={CENTER_Y}
                x2={node.x}
                y2={node.y}
                stroke={stroke}
                strokeWidth={width}
                strokeDasharray={malicious ? "none" : "4 4"}
                opacity={0.7}
                style={{ transition: "stroke 300ms ease, stroke-width 300ms ease" }}
              />
            );
          })}

          {/* Attacker hub */}
          <circle cx={CENTER_X} cy={CENTER_Y} r={48} fill="url(#atk-glow)" />
          <circle
            cx={CENTER_X}
            cy={CENTER_Y}
            r={18}
            fill="#7f1d1d"
            stroke="#EF4444"
            strokeWidth={2}
          />
          <text
            x={CENTER_X}
            y={CENTER_Y + 4}
            textAnchor="middle"
            fontSize="10"
            fontWeight={700}
            fill="#fff"
            fontFamily="ui-monospace, SFMono-Regular, monospace"
          >
            ATK
          </text>

          {/* Victim nodes */}
          {positioned.map((node) => {
            const sev = severityFromRisk(node.nodeRisk);
            const ring = severityColors[sev];
            const radius = 8 + node.nodeRisk * 16; // 8 → 24
            const fill = clusterColor(node.hostId);
            const isHover = hoverId === node.hostId;
            return (
              <g
                key={`n-${node.hostId}`}
                onMouseEnter={() => setHoverId(node.hostId)}
                onMouseLeave={() => setHoverId((cur) => (cur === node.hostId ? null : cur))}
                style={{ cursor: "pointer" }}
              >
                {/* Severity halo ring */}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={radius + 6}
                  fill="none"
                  stroke={ring.fg}
                  strokeOpacity={isHover ? 0.9 : 0.45}
                  strokeWidth={isHover ? 2 : 1}
                  style={{ transition: "r 300ms ease, stroke-opacity 200ms" }}
                />
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={radius}
                  fill={fill}
                  fillOpacity={0.85}
                  stroke="#0b1416"
                  strokeWidth={1.2}
                  style={{ transition: "r 300ms ease, fill 300ms ease" }}
                />
                <text
                  x={node.x}
                  y={node.y + radius + 12}
                  textAnchor="middle"
                  fontSize="9"
                  fill="#497f8b"
                  fontFamily="ui-monospace, SFMono-Regular, monospace"
                >
                  {node.hostId.length > 14 ? node.hostId.slice(0, 13) + "…" : node.hostId}
                </text>
                {(() => {
                  const hn = agentToHost.get(node.hostId);
                  if (!hn) return null;
                  return (
                    <text
                      x={node.x}
                      y={node.y + radius + 23}
                      textAnchor="middle"
                      fontSize="8"
                      fill="#10B981"
                      fontFamily="ui-monospace, SFMono-Regular, monospace"
                    >
                      {hn}
                    </text>
                  );
                })()}
              </g>
            );
          })}

          {/* Empty state */}
          {visible.length === 0 && (
            <text
              x={VIEW_W / 2}
              y={VIEW_H / 2}
              textAnchor="middle"
              fontSize="11"
              fill="#497f8b"
            >
              Awaiting GNN frames…
            </text>
          )}
        </svg>
        </div>

        {/*
          Hover tooltip — sibling of the clipping shell so it can extend
          past the rounded card edges. Edge-aware placement:
            * default: render above the node;
            * if the node is in the top ~28% of the SVG, flip below so the
              tooltip never collides with the graph header;
            * horizontal: clamp the centre to [15%, 85%] of the panel so
              the ~200px tooltip body never overflows left/right edges.
          z-50 keeps it on top of any neighbouring panel that happens to
          paint after this card in the dashboard grid.
        */}
        {hovered && (() => {
          const flipBelow = hovered.y < VIEW_H * 0.28;
          const leftPct = (hovered.x / VIEW_W) * 100;
          const leftClamped = Math.max(15, Math.min(85, leftPct));
          const topPct = (hovered.y / VIEW_H) * 100;
          const verticalT = flipBelow
            ? "calc(0% + 14px)"
            : "calc(-100% - 14px)";
          return (
            <div
              className="absolute z-50 pointer-events-none rounded-lg border bg-black/85 text-white text-[10px] p-2.5 shadow-xl backdrop-blur-sm"
              style={{
                left: `${leftClamped}%`,
                top: `${topPct}%`,
                transform: `translate(-50%, ${verticalT})`,
                borderColor: severityColors[severityFromRisk(hovered.nodeRisk)].border,
                minWidth: 180,
                maxWidth: 240,
              }}
            >
              <div className="font-bold mb-1.5 font-mono">{hovered.hostId}</div>
              <TooltipRow k="node_risk" v={hovered.nodeRisk.toFixed(4)} />
              <TooltipRow k="neighbor_risk" v={hovered.neighborRisk.toFixed(4)} />
              <TooltipRow k="risk_growth" v={hovered.riskGrowth.toFixed(4)} />
              <TooltipRow k="affected_edges" v={String(hovered.affectedEdges)} />
              <TooltipRow k="srcip" v={hovered.srcip ?? "—"} />
              <div className="mt-2 pt-1.5 border-t border-white/10">
                <div className="text-[8px] uppercase tracking-wider text-white/50 mb-1">
                  node_risk · last {hovered.riskHistory.length}
                </div>
                <Sparkline
                  values={hovered.riskHistory}
                  stroke={clusterColor(hovered.hostId)}
                  width={160}
                  height={22}
                />
              </div>
            </div>
          );
        })()}
      </div>

      {/* Cluster legend */}
      {clusters.length > 0 && (
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <span className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            Clusters
          </span>
          {clusters.map((c) => (
            <span
              key={c.color}
              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-[rgba(128,182,195,0.25)]"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: c.color }}
              />
              <span className="text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                ×{c.count}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function TooltipRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 font-mono leading-tight">
      <span className="text-white/55">{k}</span>
      <span>{v}</span>
    </div>
  );
}

function Sparkline({
  values,
  stroke,
  width,
  height,
}: {
  values: number[];
  stroke: string;
  width: number;
  height: number;
}) {
  if (values.length === 0) return null;
  const min = 0;
  const max = 1; // node_risk is bounded [0,1]
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  const points = values
    .map((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / (max - min)) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height}>
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth={1.2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ConfidenceGauge({ value }: { value: number }) {
  // Small donut (full ring, partial fill) instead of a half-arc. The
  // donut's bounding box is symmetric in BOTH axes, so `flex items-center`
  // centres it perfectly against text or pills next to it — half-arcs
  // had a visual bias toward the top (the arc's "ink centroid" sits
  // above the SVG's geometric centre) and looked misaligned.
  const v = Math.max(0, Math.min(1, value));
  const sev = severityFromRisk(v);
  const color = severityColors[sev].fg;
  const sw = 2.5;
  const r = 7;
  const cx = 9;
  const cy = 9;
  const size = 18;
  const C = 2 * Math.PI * r;
  return (
    <div className="inline-flex items-center gap-1.5 leading-none">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="block shrink-0"
      >
        {/* Track */}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          stroke="rgba(128,182,195,0.25)"
          strokeWidth={sw}
          fill="none"
        />
        {/* Fill — start at 12 o'clock, sweep clockwise, length proportional to v */}
        {v > 0 && (
          <circle
            cx={cx}
            cy={cy}
            r={r}
            stroke={color}
            strokeWidth={sw}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={`${(v * C).toFixed(2)} ${C.toFixed(2)}`}
            strokeDashoffset={0}
            transform={`rotate(-90 ${cx} ${cy})`}
            style={{ transition: "stroke 300ms ease, stroke-dasharray 300ms ease" }}
          />
        )}
      </svg>
      <span className="text-[10px] font-mono" style={{ color }}>
        {(v * 100).toFixed(0)}%
      </span>
    </div>
  );
}

// ---- Legacy mode (unchanged behaviour for /attack-analysis/[id]) -----------

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
};

function severityForLegacy(stage: number | undefined, fallback: string | undefined): string {
  if (fallback && fallback in SEV_RING) return fallback;
  const s = Number(stage ?? 0);
  if (s >= 7) return "critical";
  if (s >= 5) return "high";
  if (s >= 3) return "medium";
  if (s >= 1) return "low";
  return "info";
}

function isApiNode(v: unknown): v is ApiNode {
  return typeof v === "object" && v !== null && "hostId" in (v as Record<string, unknown>);
}
function isApiEdge(v: unknown): v is ApiEdge {
  return (
    typeof v === "object" &&
    v !== null &&
    "from" in (v as Record<string, unknown>) &&
    "to" in (v as Record<string, unknown>)
  );
}

function LegacyGraphEvolution({
  className,
  snapshots,
}: {
  className?: string;
  snapshots?: ApiSnapshot[] | unknown;
}) {
  const [activeTab, setActiveTab] = useState<"nodes" | "edges">("nodes");

  const list = Array.isArray(snapshots) ? (snapshots as ApiSnapshot[]) : [];

  const latest = useMemo(() => {
    for (let i = list.length - 1; i >= 0; i--) {
      const s = list[i];
      if (s && Array.isArray(s.nodes) && s.nodes.length > 0) return s;
    }
    return null;
  }, [list]);

  const nodes: ApiNode[] = useMemo(
    () => ((latest?.nodes ?? []) as unknown[]).filter(isApiNode),
    [latest],
  );
  const edges: ApiEdge[] = useMemo(
    () => ((latest?.edges ?? []) as unknown[]).filter(isApiEdge),
    [latest],
  );

  const positioned = useMemo(() => {
    const cx = 320;
    const cy = 160;
    const r = 110;
    const n = Math.max(nodes.length, 1);
    return nodes.map((node, i) => {
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
      return {
        ...node,
        x: cx + Math.cos(angle) * r - 60,
        y: cy + Math.sin(angle) * r - 22,
      };
    });
  }, [nodes]);

  const nodeById = useMemo(() => {
    const m = new Map<string, (typeof positioned)[number]>();
    positioned.forEach((p) => m.set(p.hostId, p));
    return m;
  }, [positioned]);

  return (
    <div className={cn("w-full", className)}>
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
                : "text-[#497f8b] dark:text-[var(--strix-text-muted)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] hover:bg-gray-50 dark:hover:bg-gray-800",
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
                : "text-[#497f8b] dark:text-[var(--strix-text-muted)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] hover:bg-gray-50 dark:hover:bg-gray-800",
            )}
          >
            Edges ({edges.length})
          </button>
        </div>
      </div>

      <div className="relative w-full h-[320px] bg-[#e7faff]/50 dark:bg-[var(--strix-bg-surface)] rounded-[32px] overflow-hidden border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
        <svg className="absolute inset-0 w-full h-full opacity-15">
          <defs>
            <pattern id="graph-grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#497f8b" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#graph-grid)" />
        </svg>

        {nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            No graph data for this chain in window.
          </div>
        )}

        {edges.length > 0 && (
          <svg className="absolute inset-0 w-full h-full">
            {edges.map((edge, i) => {
              const a = nodeById.get(edge.from);
              const b = nodeById.get(edge.to);
              if (!a || !b) return null;
              const malicious = edge.type !== "normal";
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
              );
            })}
          </svg>
        )}

        {positioned.map((node) => {
          const sev = severityForLegacy(node.ckcStage, node.severity);
          const styles = SEV_RING[sev] ?? SEV_RING.info;
          const label = node.hostName ?? node.hostId;
          const sublabel = node.ckcStage != null ? `stage ${node.ckcStage}` : sev.toUpperCase();
          return (
            <div key={node.hostId} className="absolute" style={{ left: node.x, top: node.y }}>
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
          );
        })}
      </div>
    </div>
  );
}
