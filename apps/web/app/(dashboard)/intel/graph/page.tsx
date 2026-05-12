// /intel/graph — pivot graph of the CTI surface.
//
// Layout: radial concentric, deterministic (no force simulation needed
// at this scale). Actors are placed evenly on an inner ring; each
// campaign is anchored on the middle ring at its actor's angle; each
// chain sits on the outer ring near its campaign. Edges drawn as
// quadratic Béziers through the centroid for a "real CTI graph"
// silhouette.
//
// Click a node → drill-down to its detail page.

"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useIntelGraph, type GraphEdge, type GraphNode } from "@/lib/api/intel";

const CX = 480;
const CY = 320;
const R_ACTOR = 90;
const R_CAMPAIGN = 200;
const R_CHAIN = 320;

interface PositionedNode extends GraphNode {
  x: number;
  y: number;
  angle: number; // radians
}

function buildLayout(nodes: GraphNode[], edges: GraphEdge[]): PositionedNode[] {
  const actors = nodes.filter((n) => n.type === "actor");
  const campaigns = nodes.filter((n) => n.type === "campaign");
  const chains = nodes.filter((n) => n.type === "chain");

  const positioned: PositionedNode[] = [];

  // 1. Actors evenly spaced on the inner ring.
  const actorAngle: Record<string, number> = {};
  actors.forEach((a, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, actors.length) - Math.PI / 2;
    actorAngle[a.id] = angle;
    positioned.push({
      ...a,
      angle,
      x: CX + R_ACTOR * Math.cos(angle),
      y: CY + R_ACTOR * Math.sin(angle),
    });
  });

  // 2. Campaigns anchored near their actor. Edges of type
  //    `attributed-to` from campaign → actor give us the actor parent.
  const campaignParent: Record<string, string> = {};
  edges.forEach((e) => {
    // The campaign-side endpoint isn't tagged in the edge schema; we
    // figure it out by joining IDs to node types.
    const from = nodes.find((n) => n.id === e.fromId);
    const to = nodes.find((n) => n.id === e.toId);
    if (from?.type === "campaign" && to?.type === "actor") {
      campaignParent[from.id] = to.id;
    }
  });

  // Group campaigns per actor, spread within a small angular slice.
  const byActor: Record<string, string[]> = {};
  campaigns.forEach((c) => {
    const parent = campaignParent[c.id] ?? actors[0]?.id ?? "";
    (byActor[parent] ||= []).push(c.id);
  });

  const campaignAngle: Record<string, number> = {};
  campaigns.forEach((c) => {
    const parent = campaignParent[c.id];
    const baseAngle = parent ? actorAngle[parent] : 0;
    const peers = byActor[parent ?? ""] ?? [c.id];
    const idx = peers.indexOf(c.id);
    const spread = 0.35; // radians
    const offset =
      peers.length > 1
        ? -spread / 2 + (spread * idx) / (peers.length - 1)
        : 0;
    const angle = baseAngle + offset;
    campaignAngle[c.id] = angle;
    positioned.push({
      ...c,
      angle,
      x: CX + R_CAMPAIGN * Math.cos(angle),
      y: CY + R_CAMPAIGN * Math.sin(angle),
    });
  });

  // 3. Chains near their campaign. Same pattern.
  const chainParent: Record<string, string> = {};
  edges.forEach((e) => {
    const from = nodes.find((n) => n.id === e.fromId);
    const to = nodes.find((n) => n.id === e.toId);
    if (from?.type === "chain" && to?.type === "campaign") {
      chainParent[from.id] = to.id;
    }
  });

  const byCampaign: Record<string, string[]> = {};
  chains.forEach((c) => {
    const parent = chainParent[c.id] ?? campaigns[0]?.id ?? "";
    (byCampaign[parent] ||= []).push(c.id);
  });

  chains.forEach((c) => {
    const parent = chainParent[c.id];
    const baseAngle = parent ? campaignAngle[parent] : 0;
    const peers = byCampaign[parent ?? ""] ?? [c.id];
    const idx = peers.indexOf(c.id);
    const spread = 0.45;
    const offset =
      peers.length > 1
        ? -spread / 2 + (spread * idx) / (peers.length - 1)
        : 0;
    const angle = baseAngle + offset;
    positioned.push({
      ...c,
      angle,
      x: CX + R_CHAIN * Math.cos(angle),
      y: CY + R_CHAIN * Math.sin(angle),
    });
  });

  return positioned;
}

const NODE_STYLES: Record<string, { fill: string; stroke: string; r: number }> = {
  actor: { fill: "#c44", stroke: "#fff", r: 22 },
  campaign: { fill: "#00666d", stroke: "#87edf6", r: 14 },
  chain: { fill: "#1a2730", stroke: "#87edf6", r: 8 },
  indicator: { fill: "#2a8", stroke: "#fff", r: 6 },
  host: { fill: "#497f8b", stroke: "#fff", r: 6 },
};

function nodeHref(n: GraphNode): string | null {
  switch (n.type) {
    case "actor": return `/intel/actors/${n.id}`;
    case "campaign": return `/intel/campaigns/${n.id}`;
    case "chain": return `/attack-analysis/${n.id}`;
    default: return null;
  }
}

export default function IntelGraphPage() {
  const { data, isLoading } = useIntelGraph(30);
  const [hovered, setHovered] = useState<string | null>(null);

  const positioned = useMemo(
    () => buildLayout(data?.nodes ?? [], data?.edges ?? []),
    [data?.nodes, data?.edges],
  );
  const indexed = useMemo(() => {
    const m = new Map<string, PositionedNode>();
    positioned.forEach((n) => m.set(n.id, n));
    return m;
  }, [positioned]);

  return (
    <div className="min-w-[1280px] space-y-4">
      <div className="flex items-center justify-between bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-3">
        <div>
          <p className="text-[10px] text-[#00666d] dark:text-strix-cyan uppercase tracking-[1.2px] font-bold mb-1">
            <Link href="/intel" className="hover:underline">Threat Intel</Link> · Pivot Graph
          </p>
          <h1 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            Knowledge Graph
          </h1>
        </div>
        <Legend />
      </div>

      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-4">
        {isLoading ? (
          <div className="h-[640px] flex items-center justify-center text-[#497f8b] text-sm">
            Loading graph…
          </div>
        ) : positioned.length === 0 ? (
          <div className="h-[640px] flex items-center justify-center text-[#497f8b] text-sm italic">
            No graph data yet — run `bash jury_demo.sh --apt all` to populate.
          </div>
        ) : (
          <svg viewBox="0 0 960 640" className="w-full h-[640px]">
            {/* Faint guide rings */}
            <circle cx={CX} cy={CY} r={R_ACTOR} fill="none" stroke="rgba(128,182,195,0.08)" strokeDasharray="2 4" />
            <circle cx={CX} cy={CY} r={R_CAMPAIGN} fill="none" stroke="rgba(128,182,195,0.08)" strokeDasharray="2 4" />
            <circle cx={CX} cy={CY} r={R_CHAIN} fill="none" stroke="rgba(128,182,195,0.08)" strokeDasharray="2 4" />

            {/* Edges */}
            {(data?.edges ?? []).map((e, i) => {
              const a = indexed.get(e.fromId);
              const b = indexed.get(e.toId);
              if (!a || !b) return null;
              const isHot = hovered === a.id || hovered === b.id;
              // Curve via centroid for visual lift.
              const mx = (a.x + b.x) / 2;
              const my = (a.y + b.y) / 2;
              const dx = mx - CX;
              const dy = my - CY;
              const dist = Math.sqrt(dx * dx + dy * dy) || 1;
              const cx = mx - (dx / dist) * 20;
              const cy = my - (dy / dist) * 20;
              return (
                <path
                  key={`e-${i}`}
                  d={`M ${a.x},${a.y} Q ${cx},${cy} ${b.x},${b.y}`}
                  fill="none"
                  stroke={isHot ? "#87edf6" : "rgba(128,182,195,0.18)"}
                  strokeWidth={isHot ? 1.4 : 0.8}
                  opacity={Math.min(1, 0.3 + e.confidence / 200)}
                />
              );
            })}

            {/* Nodes */}
            {positioned.map((n) => {
              const style = NODE_STYLES[n.type] ?? NODE_STYLES.indicator;
              const href = nodeHref(n);
              const inner = (
                <g
                  onMouseEnter={() => setHovered(n.id)}
                  onMouseLeave={() => setHovered(null)}
                  className="cursor-pointer"
                >
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={style.r + (hovered === n.id ? 2 : 0)}
                    fill={style.fill}
                    stroke={style.stroke}
                    strokeWidth={hovered === n.id ? 2 : 1}
                  />
                  {n.type === "actor" && (
                    <text
                      x={n.x}
                      y={n.y + 4}
                      textAnchor="middle"
                      fontSize={10}
                      fontWeight={700}
                      fill="#fff"
                    >
                      {n.label}
                    </text>
                  )}
                  {n.type !== "chain" && (
                    <text
                      x={n.x}
                      y={n.y + style.r + 12}
                      textAnchor="middle"
                      fontSize={9}
                      fill="#497f8b"
                    >
                      {n.type === "actor" ? n.badge ?? "" : n.label.slice(0, 30)}
                    </text>
                  )}
                </g>
              );
              return href ? (
                <Link key={n.id} href={href}>
                  {inner}
                </Link>
              ) : (
                <g key={n.id}>{inner}</g>
              );
            })}
          </svg>
        )}
      </div>

      {hovered && (
        <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-3">
          <NodeDetail node={indexed.get(hovered) ?? null} />
        </div>
      )}
    </div>
  );
}

function NodeDetail({ node }: { node: PositionedNode | null }) {
  if (!node) return null;
  const href = nodeHref(node);
  return (
    <div className="flex items-center gap-3 text-[12px]">
      <span className="text-[9px] uppercase tracking-wider text-[#497f8b]">{node.type}</span>
      <span className="font-bold text-[#00343d] dark:text-[var(--strix-text)]">{node.label}</span>
      {node.subLabel && <span className="text-[#497f8b]">· {node.subLabel}</span>}
      {node.badge && <span className="font-mono text-[10px] text-[#497f8b]">· {node.badge}</span>}
      <span className="ml-auto text-[10px] text-[#497f8b]">score {node.score}</span>
      {href && (
        <Link href={href} className="text-[#00666d] dark:text-strix-cyan hover:underline">
          open →
        </Link>
      )}
    </div>
  );
}

function Legend() {
  return (
    <div className="flex items-center gap-3 text-[10px] text-[#497f8b]">
      <Dot fill="#c44" /> actor
      <Dot fill="#00666d" /> campaign
      <Dot fill="#1a2730" stroke="#87edf6" /> chain
    </div>
  );
}

function Dot({ fill, stroke }: { fill: string; stroke?: string }) {
  return (
    <span
      className="inline-block w-2.5 h-2.5 rounded-full"
      style={{ backgroundColor: fill, border: stroke ? `1px solid ${stroke}` : undefined }}
    />
  );
}
