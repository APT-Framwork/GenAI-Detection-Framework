// -----------------------------------------------------------------------------
// simulation-topology-panel.tsx (Phase 5).
//
// Live attacker → victim topology view for the dashboard.
//
// Data sources:
//   * `/api/v1/simulation/runs/latest` — initial fetch, so the panel paints
//     before the first WebSocket frame arrives.
//   * `useLogStream(["topology", "raw_log"])` — keeps the topology in sync
//     across runs (run_id change → re-fetch initial state visually) and
//     drives per-event pulses + counters.
//
// Visual:
//   * SVG with attacker on the left, victims stacked on the right.
//   * Animated dot-flow along each edge (continuous SVG <animateMotion>).
//   * Pulse on a victim node when a malicious raw_log arrives for it.
//   * Soft shimmer on a victim node when a benign raw_log arrives.
//   * Bottom strip: total / malicious / benign / alerts counters, reset on
//     run_id change so they reflect ONE simulation run, not a session-wide
//     accumulation.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Bug, Server, Shield, Zap } from "lucide-react";

import { useLatestSimulationRun } from "@/lib/api/simulation";
import {
  useLogStream,
  type EnvelopeOf,
  type RawLogPayload,
  type TopologyPayload,
  type TopologyVictim,
} from "@/lib/api/ws";
import { severityColors } from "@/lib/design-tokens";
import { cn } from "@/lib/utils";
import {
  usePredetections,
  type Predetection,
} from "@/lib/predetection-store";
import { recordHostAgent, useHostAgentMap } from "@/lib/host-agent-map";

const STAGE_LABELS = ["Recon", "Weapon", "Delivery", "Exploit", "Install", "C2", "Action"];

function matchPredetection(
  v: TopologyVictim,
  preds: ReadonlyMap<string, Predetection>,
  hostToAgent: ReadonlyMap<string, string>,
): Predetection | undefined {
  // Two ID spaces in play:
  //   * topology.json carries victims by hostname/ip ("victim1", "172.20.0.5").
  //   * RL frames key by `msg.agent_id` — the *wazuh* numeric agent id
  //     ("008") on lab data, not the hostname.
  // We try the direct candidates first, then fall back to the runtime
  // host-agent bridge (`host-agent-map.ts`) which learns the mapping from
  // raw_log frames. Without this, predetections never match a topology
  // node and the BLOCKED edge never renders.
  const candidates = [v.agent_id, v.hostname, v.name, v.ip, ...(v.agents ?? [])];
  for (const c of candidates) {
    if (!c) continue;
    if (preds.has(c)) return preds.get(c);
    const bridged = hostToAgent.get(c);
    if (bridged && preds.has(bridged)) return preds.get(bridged);
  }
  return undefined;
}

const PULSE_MS = 700;

interface Counters {
  total: number;
  malicious: number;
  benign: number;
  alerts: number;
}

const ZERO_COUNTERS: Counters = { total: 0, malicious: 0, benign: 0, alerts: 0 };

// GNN threshold echoed from the backend (apps/api/.../streams.py).
const GNN_RISK_ALERT_THRESHOLD = 0.7743;

export function SimulationTopologyPanel({ className }: { className?: string }) {
  const initial = useLatestSimulationRun();
  const stream = useLogStream(["topology", "raw_log"]);

  // Resolve the current topology: prefer the latest WS frame, fall back to
  // the initial REST snapshot.
  const topology: TopologyPayload | null = useMemo(() => {
    const wsFrames = stream.frames.topology;
    if (wsFrames.length > 0) return wsFrames[wsFrames.length - 1].payload;
    return initial.data?.topology ?? null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial.data, stream.seq.topology]);

  const runId = topology?.run_id ?? null;

  // Counters reset whenever run_id changes.
  const [counters, setCounters] = useState<Counters>(ZERO_COUNTERS);
  const lastRunIdRef = useRef<string | null>(null);
  const lastSeenSeqRef = useRef<number>(0);
  // Per-victim pulse state: hostname → { ts, kind }.
  const [pulses, setPulses] = useState<Record<string, { ts: number; kind: "malicious" | "benign" }>>({});

  // Drain raw_log frames as they arrive. We track which seq we've already
  // consumed; on a new seq, only the *new* tail of the buffer is processed
  // so a single event isn't counted twice.
  useEffect(() => {
    const seq = stream.seq.raw_log ?? 0;
    if (seq === lastSeenSeqRef.current && runId === lastRunIdRef.current) return;

    if (runId !== lastRunIdRef.current) {
      lastRunIdRef.current = runId;
      setCounters(ZERO_COUNTERS);
      // Don't re-process backlog from the previous run.
      lastSeenSeqRef.current = seq;
      return;
    }

    const buf = stream.frames.raw_log;
    const consumeFrom = Math.max(0, buf.length - (seq - lastSeenSeqRef.current));
    const fresh = buf.slice(consumeFrom);
    lastSeenSeqRef.current = seq;
    if (fresh.length === 0) return;

    let dTotal = 0,
      dMal = 0,
      dBen = 0,
      dAlert = 0;
    const newPulses: Record<string, { ts: number; kind: "malicious" | "benign" }> = {};

    for (const frame of fresh) {
      const p = frame.payload;
      dTotal += 1;
      const isMal = isMalicious(p);
      const isAlert = (p.gnnNodeRisk ?? 0) >= GNN_RISK_ALERT_THRESHOLD;
      if (isMal) dMal += 1;
      else dBen += 1;
      if (isAlert) dAlert += 1;

      const target = victimKey(topology, p);
      if (target) {
        newPulses[target] = { ts: Date.now(), kind: isMal ? "malicious" : "benign" };
      }
      // Learn the agent_id ↔ hostname join ONLY from strictly-matched
      // frames. The lenient `victimKey` falls back to victims[0] when
      // it can't attribute a frame, which would (and did) collapse
      // every agent_id onto the same hostname in the GNN labels.
      const aid = p.agentId ?? p.agent_id ?? null;
      const strictTarget = victimKeyStrict(topology, p);
      if (aid && strictTarget) recordHostAgent(aid, strictTarget);
    }

    setCounters((c) => ({
      total: c.total + dTotal,
      malicious: c.malicious + dMal,
      benign: c.benign + dBen,
      alerts: c.alerts + dAlert,
    }));
    if (Object.keys(newPulses).length > 0) {
      setPulses((prev) => ({ ...prev, ...newPulses }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.seq.raw_log, runId]);

  // Expire pulses after PULSE_MS so the visual is transient.
  useEffect(() => {
    if (Object.keys(pulses).length === 0) return;
    const id = setInterval(() => {
      const cutoff = Date.now() - PULSE_MS;
      setPulses((prev) => {
        let changed = false;
        const next: typeof prev = {};
        for (const [k, v] of Object.entries(prev)) {
          if (v.ts > cutoff) next[k] = v;
          else changed = true;
        }
        return changed ? next : prev;
      });
    }, 200);
    return () => clearInterval(id);
  }, [pulses]);

  return (
    <div
      className={cn(
        "bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-[24px] p-6",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-[10px] text-[#00666d] dark:text-strix-cyan uppercase tracking-[1.2px] font-bold mb-1">
            SIMULATION TOPOLOGY
          </p>
          <h3 className="text-lg font-bold text-[#00343d] dark:text-[var(--strix-text)] font-heading">
            {topology?.apt_group || topology?.apt || (initial.isLoading ? "loading…" : "no active run")}
          </h3>
          {topology && (
            <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5">
              run {runId} · started {formatStarted(topology.started_at)}
            </p>
          )}
        </div>
        {topology?.tactics_planned && topology.tactics_planned.length > 0 && (
          <div className="flex flex-wrap gap-1.5 max-w-[55%] justify-end">
            {topology.tactics_planned.slice(0, 6).map((t) => (
              <span
                key={t}
                className="rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider bg-[#00666d]/10 text-[#00666d] dark:bg-strix-cyan/10 dark:text-strix-cyan border border-[#00666d]/20"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* SVG canvas */}
      <TopologySvg topology={topology} pulses={pulses} predetections={usePredetections()} hostToAgent={useHostAgentMap().hostToAgent} />

      {/* Counters strip */}
      <div className="grid grid-cols-4 gap-3 mt-5">
        <Counter label="Total" value={counters.total} icon={Server} fg="#3B82F6" />
        <Counter label="Malicious" value={counters.malicious} icon={Bug} fg={severityColors.critical.fg} />
        <Counter label="Benign" value={counters.benign} icon={Shield} fg={severityColors.benign.fg} />
        <Counter label="Alerts" value={counters.alerts} icon={Zap} fg={severityColors.high.fg} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SVG
// ---------------------------------------------------------------------------

const W = 640;
const H = 280;
const ATTACKER_X = 80;
const VICTIM_X = 540;

function TopologySvg({
  topology,
  pulses,
  predetections,
  hostToAgent,
}: {
  topology: TopologyPayload | null;
  pulses: Record<string, { ts: number; kind: "malicious" | "benign" }>;
  predetections: ReadonlyMap<string, Predetection>;
  hostToAgent: ReadonlyMap<string, string>;
}) {
  const victims = topology?.victims ?? [];

  if (!topology || victims.length === 0) {
    return (
      <div className="h-[280px] flex items-center justify-center text-[#497f8b] dark:text-[var(--strix-text-muted)] text-sm italic">
        waiting for a simulation run…
      </div>
    );
  }

  const ay = H / 2;
  const step = victims.length === 1 ? 0 : (H - 80) / (victims.length - 1);
  const positions = victims.map((_, i) => 40 + i * step);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[280px]" role="img" aria-label="Simulation topology">
      <defs>
        <radialGradient id="attackerGlow">
          <stop offset="0%" stopColor="#EF4444" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#EF4444" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="victimGlow">
          <stop offset="0%" stopColor="#00F2FF" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#00F2FF" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Edges */}
      {victims.map((v, i) => {
        const vy = positions[i];
        const id = `edge-${i}`;
        const path = `M ${ATTACKER_X} ${ay} L ${VICTIM_X} ${vy}`;
        const key = victimNodeKey(v);
        const pulse = key ? pulses[key] : undefined;
        const pred = matchPredetection(v, predetections, hostToAgent);
        // Predetected victim → freeze the dot animation, swap to dashed
        // emerald edge labelled BLOCKED. The asymmetry between blocked and
        // still-flowing edges is the credibility hook: the jury sees one
        // host's attack stopped while another's continues until its own
        // predetection lands.
        if (pred) {
          const midX = (ATTACKER_X + VICTIM_X) / 2;
          const midY = (ay + vy) / 2;
          return (
            <g key={id}>
              <path
                d={path}
                stroke="#10B981"
                strokeWidth={2}
                strokeDasharray="6 4"
                fill="none"
                opacity={0.85}
              />
              <rect
                x={midX - 50}
                y={midY - 9}
                width={100}
                height={18}
                rx={9}
                fill="rgba(16,185,129,0.18)"
                stroke="#10B981"
                strokeWidth={1}
              />
              <text
                x={midX}
                y={midY + 3.5}
                textAnchor="middle"
                fontSize={9}
                fontWeight={700}
                fill="#10B981"
                style={{ fontFamily: "ui-monospace, monospace" }}
              >
                ⛨ BLOCKED · {STAGE_LABELS[Math.max(0, pred.stage - 1)] ?? "?"}
              </text>
            </g>
          );
        }
        const stroke = pulse?.kind === "malicious" ? severityColors.critical.fg : "rgba(0,242,255,0.35)";
        return (
          <g key={id}>
            <path d={path} stroke={stroke} strokeWidth={pulse?.kind === "malicious" ? 2 : 1.25} fill="none" id={id} />
            {[0, 0.33, 0.66].map((begin) => (
              <circle key={begin} r={3} fill={stroke}>
                <animateMotion dur="2.4s" repeatCount="indefinite" begin={`${begin * 2.4}s`}>
                  <mpath href={`#${id}`} />
                </animateMotion>
              </circle>
            ))}
          </g>
        );
      })}

      {/* Attacker */}
      <g>
        <circle cx={ATTACKER_X} cy={ay} r={42} fill="url(#attackerGlow)" />
        <circle cx={ATTACKER_X} cy={ay} r={22} fill="#1F0A0A" stroke="#EF4444" strokeWidth={2} />
        <text x={ATTACKER_X} y={ay + 5} textAnchor="middle" fontSize={11} fontWeight={700} fill="#EF4444" style={{ fontFamily: "monospace" }}>
          ATK
        </text>
        <text x={ATTACKER_X} y={ay + 50} textAnchor="middle" fontSize={10} fill="#94A3B8" style={{ fontFamily: "monospace" }}>
          {topology.attacker_ip}
        </text>
      </g>

      {/* Victims */}
      {victims.map((v, i) => {
        const vy = positions[i];
        const key = victimNodeKey(v) ?? `v${i}`;
        const pulse = pulses[key];
        const isMal = pulse?.kind === "malicious";
        const pred = matchPredetection(v, predetections, hostToAgent);
        const ringColor = pred ? "#10B981" : isMal ? severityColors.critical.fg : "#00F2FF";
        return (
          <g key={key}>
            {/* Steady protective halo when predetected. */}
            {pred && (
              <circle
                cx={VICTIM_X}
                cy={vy}
                r={48}
                fill="rgba(16,185,129,0.10)"
                stroke="rgba(16,185,129,0.45)"
                strokeWidth={1.5}
                strokeDasharray="3 3"
              >
                <animate
                  attributeName="r"
                  values="44;52;44"
                  dur="2.6s"
                  repeatCount="indefinite"
                />
              </circle>
            )}
            {pulse && !pred && (
              <circle
                cx={VICTIM_X}
                cy={vy}
                r={36}
                fill={isMal ? "rgba(239,68,68,0.30)" : "rgba(59,130,246,0.20)"}
              >
                <animate attributeName="r" from="22" to="48" dur={`${PULSE_MS}ms`} fill="freeze" />
                <animate attributeName="opacity" from="0.8" to="0" dur={`${PULSE_MS}ms`} fill="freeze" />
              </circle>
            )}
            <circle
              cx={VICTIM_X}
              cy={vy}
              r={42}
              fill="url(#victimGlow)"
              opacity={pred ? 0.4 : pulse ? 1 : 0.6}
            />
            <circle
              cx={VICTIM_X}
              cy={vy}
              r={22}
              fill={pred ? "#062017" : "#0A1628"}
              stroke={ringColor}
              strokeWidth={pred ? 2.5 : 2}
            />
            <text
              x={VICTIM_X}
              y={vy + 5}
              textAnchor="middle"
              fontSize={11}
              fontWeight={700}
              fill={pred ? "#10B981" : "#00F2FF"}
              style={{ fontFamily: "monospace" }}
            >
              {pred ? "⛨" : (v.hostname ?? v.name ?? `V${i + 1}`).slice(0, 8)}
            </text>
            {pred && (
              <text
                x={VICTIM_X}
                y={vy - 30}
                textAnchor="middle"
                fontSize={8}
                fontWeight={700}
                fill="#10B981"
                style={{ fontFamily: "monospace" }}
              >
                PROTECTED · {(pred.elapsedMs / 1000).toFixed(1)}s
              </text>
            )}
            <text x={VICTIM_X} y={vy + 50} textAnchor="middle" fontSize={10} fill="#94A3B8" style={{ fontFamily: "monospace" }}>
              {v.ip}
            </text>
            {(() => {
              const aid = (v.hostname && hostToAgent.get(v.hostname)) || (v.name && hostToAgent.get(v.name)) || null;
              if (!aid) return null;
              return (
                <text
                  x={VICTIM_X}
                  y={vy + 78}
                  textAnchor="middle"
                  fontSize={9}
                  fontWeight={700}
                  fill="#10B981"
                  style={{ fontFamily: "monospace" }}
                >
                  agent {aid}
                </text>
              );
            })()}
            {/* Agent badges below */}
            <g>
              {(v.agents ?? []).slice(0, 3).map((agent, j) => (
                <text
                  key={agent}
                  x={VICTIM_X + (j - 1) * 36}
                  y={vy + 64}
                  textAnchor="middle"
                  fontSize={8}
                  fill="#64748B"
                  style={{ fontFamily: "monospace" }}
                >
                  {agent}
                </text>
              ))}
            </g>
          </g>
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Counter card
// ---------------------------------------------------------------------------

function Counter({
  label,
  value,
  icon: Icon,
  fg,
}: {
  label: string;
  value: number;
  icon: typeof Server;
  fg: string;
}) {
  return (
    <div className="rounded-xl border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] px-3 py-2 flex items-center gap-2.5 bg-[var(--strix-bg-surface)]/40">
      <Icon size={14} style={{ color: fg }} />
      <div className="flex-1 min-w-0">
        <div
          className="text-[9px] uppercase tracking-wider font-semibold"
          style={{ color: fg }}
        >
          {label}
        </div>
        <div className="text-base font-bold text-[#00343d] dark:text-[var(--strix-text)] tabular-nums">
          {value.toLocaleString()}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function isMalicious(p: RawLogPayload): boolean {
  if (typeof p.ckcStage === "number" && p.ckcStage > 0) return true;
  if (typeof p.gnnNodeRisk === "number" && p.gnnNodeRisk >= GNN_RISK_ALERT_THRESHOLD) return true;
  if (p.synthetic_benign) return false;
  return false;
}

function victimNodeKey(v: TopologyVictim): string | null {
  return v.hostname ?? v.name ?? v.ip ?? null;
}

/** Strict match — returns null if the frame can't be tied to a specific
 *  victim. Use this when correctness matters (e.g. learning the
 *  agent_id ↔ hostname mapping for the GNN labels). */
function victimKeyStrict(topo: TopologyPayload | null, p: RawLogPayload): string | null {
  if (!topo?.victims) return null;
  const agentId = p.agentId ?? p.agent_id ?? null;
  const ip = p.srcip ?? p.src_ip ?? null;
  for (const v of topo.victims) {
    const key = victimNodeKey(v);
    if (!key) continue;
    if (agentId && (v.agent_id === agentId || v.hostname === agentId || v.name === agentId)) return key;
    if (agentId && Array.isArray(v.agents) && v.agents.includes(agentId)) return key;
    if (ip && v.ip === ip) return key;
  }
  return null;
}

/** Match a raw_log frame's agent/ip onto one of the topology victims.
 *  Falls back to the first victim so a pulse still renders even when the
 *  frame can't be uniquely attributed — visual-only, not authoritative. */
function victimKey(topo: TopologyPayload | null, p: RawLogPayload): string | null {
  const strict = victimKeyStrict(topo, p);
  if (strict) return strict;
  const first = topo?.victims?.[0];
  return first ? victimNodeKey(first) : null;
}

function formatStarted(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(11, 19);
}

// Re-exported so consumers can satisfy strict-mode imports if needed.
export type { EnvelopeOf };
