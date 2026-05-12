// Five live-inference panels for /ai-engine — one per model.
//
// Each panel consumes the SSE live-feed buffer, derives its own
// per-model signals from the most-recent N events, and renders a
// hero metric + small chart + footer with the source alert/age.
//
// All five share the PanelShell + Sparkline + MeterRow primitives so
// the layout stays cohesive at a glance.

"use client";

import { useMemo } from "react";
import type { LiveFeedEvent } from "@/lib/api/live-feed";
import {
  HeroNumber,
  MeterRow,
  PanelShell,
  Sparkline,
  fmtAgo,
} from "./shared";

const CKC_NAMES = [
  "BENIGN",
  "Recon",
  "Weaponization",
  "Delivery",
  "Exploitation",
  "Installation",
  "C2",
  "Actions",
];

// ---------------------------------------------------------------- AE panel


export function AePanel({
  events,
  active,
}: {
  events: LiveFeedEvent[];
  active: boolean;
}) {
  const latest = events[0];
  const anomaly = latest?.aeAnomalyScore ?? null;
  const reconErr = latest?.aeReconError ?? null;
  const recent = events.slice(0, 40);
  const anomalies = useMemo(
    () => recent.map((e) => e.aeAnomalyScore ?? 0).reverse(),
    [recent],
  );

  // Tone: AE thresholds (typical lab range 0.0-1.0 normalised).
  const tone = anomaly == null ? "default" : anomaly >= 0.7 ? "high" : anomaly >= 0.4 ? "mid" : "low";
  const label = anomaly == null ? "Awaiting input" : anomaly >= 0.7 ? "Anomalous" : anomaly >= 0.4 ? "Suspicious" : "Within profile";

  return (
    <PanelShell
      title="Autoencoder"
      subtitle="Behavioural baseline · recon error"
      accent="cyan"
      active={active}
      footer={
        latest
          ? `${latest.alertId.slice(0, 12)}… · ${fmtAgo(latest.occurredAt)}`
          : "Idle"
      }
    >
      <div className="space-y-3">
        <div className="flex items-end justify-between">
          <HeroNumber
            value={anomaly == null ? "—" : anomaly.toFixed(2)}
            unit="score"
            tone={tone as "default" | "high" | "mid" | "low"}
          />
          <span className={`text-[10px] uppercase tracking-wider font-bold ${
            tone === "high" ? "text-rose-400"
            : tone === "mid" ? "text-amber-400"
            : tone === "low" ? "text-emerald-400"
            : "text-[var(--strix-text-muted)]"
          }`}>
            {label}
          </span>
        </div>
        <Sparkline values={anomalies} max={1} colour="#87edf6" />
        <MeterRow
          label="Recon err"
          value={reconErr}
          max={1}
          format={(v) => v.toFixed(3)}
          fillCls="bg-strix-cyan/70"
        />
      </div>
    </PanelShell>
  );
}

// ---------------------------------------------------------------- VAE panel


export function VaePanel({
  events,
  active,
}: {
  events: LiveFeedEvent[];
  active: boolean;
}) {
  const latest = events[0];
  const prob = latest?.vaeMaliciousProb ?? null;
  const unc = latest?.vaeUncertainty ?? null;
  const probs = useMemo(
    () => events.slice(0, 40).map((e) => e.vaeMaliciousProb ?? 0).reverse(),
    [events],
  );
  const tone = prob == null ? "default" : prob >= 0.7 ? "high" : prob >= 0.4 ? "mid" : "low";
  const pct = prob == null ? "—" : `${Math.round(prob * 100)}`;
  const label = prob == null ? "Awaiting" : prob >= 0.7 ? "Likely malicious" : prob >= 0.4 ? "Suspicious" : "Likely benign";

  return (
    <PanelShell
      title="VAE"
      subtitle="Variational classifier · malicious prob"
      accent="purple"
      active={active}
      footer={
        latest
          ? `${latest.alertId.slice(0, 12)}… · ${fmtAgo(latest.occurredAt)}`
          : "Idle"
      }
    >
      <div className="space-y-3">
        <div className="flex items-end justify-between">
          <HeroNumber value={pct} unit="%" tone={tone as "default" | "high" | "mid" | "low"} />
          <span className={`text-[10px] uppercase tracking-wider font-bold ${
            tone === "high" ? "text-rose-400"
            : tone === "mid" ? "text-amber-400"
            : tone === "low" ? "text-emerald-400"
            : "text-[var(--strix-text-muted)]"
          }`}>
            {label}
          </span>
        </div>
        <Sparkline values={probs} max={1} colour="#c084fc" />
        <MeterRow
          label="Uncertainty"
          value={unc}
          max={1}
          format={(v) => v.toFixed(3)}
          fillCls="bg-purple-400/60"
        />
      </div>
    </PanelShell>
  );
}

// ---------------------------------------------------------------- GNN panel


export function GnnPanel({
  events,
  active,
}: {
  events: LiveFeedEvent[];
  active: boolean;
}) {
  const latest = events[0];
  const node = latest?.gnnNodeRisk ?? null;
  const neighbour = latest?.gnnNeighborRisk ?? null;
  const growth = latest?.gnnRiskGrowth ?? null;
  const risks = useMemo(
    () => events.slice(0, 40).map((e) => e.gnnNodeRisk ?? 0).reverse(),
    [events],
  );
  const tone = node == null ? "default" : node >= 0.7 ? "high" : node >= 0.4 ? "mid" : "low";
  const growthLabel = growth == null ? "—" : growth > 0.05 ? `↑ ${(growth * 100).toFixed(1)}%` : growth < -0.05 ? `↓ ${(growth * 100).toFixed(1)}%` : "≈ flat";
  const growthCls = growth == null ? "text-[var(--strix-text-muted)]" : growth > 0.05 ? "text-rose-400" : growth < -0.05 ? "text-emerald-400" : "text-[var(--strix-text-muted)]";

  return (
    <PanelShell
      title="GNN"
      subtitle="Graph propagation · 1-hop neighbourhood"
      accent="amber"
      active={active}
      footer={
        latest
          ? `${latest.alertId.slice(0, 12)}… · ${fmtAgo(latest.occurredAt)}`
          : "Idle"
      }
    >
      <div className="space-y-3">
        <div className="flex items-end justify-between">
          <HeroNumber
            value={node == null ? "—" : node.toFixed(2)}
            unit="node risk"
            tone={tone as "default" | "high" | "mid" | "low"}
          />
          <span className={`text-[10px] font-mono font-bold ${growthCls}`}>
            {growthLabel}
          </span>
        </div>
        <Sparkline values={risks} max={1} colour="#fbbf24" />
        <MeterRow
          label="Neighbour"
          value={neighbour}
          max={1}
          format={(v) => v.toFixed(2)}
          fillCls="bg-amber-400/70"
        />
      </div>
    </PanelShell>
  );
}

// ---------------------------------------------------------------- Transformer panel


export function TransformerPanel({
  events,
  active,
}: {
  events: LiveFeedEvent[];
  active: boolean;
}) {
  const latest = events[0];
  const pred = latest?.transformerPredCkc ?? null;
  const conf = latest?.transformerConfidence ?? null;
  const current = latest?.ckcStage ?? null;
  const predName = pred != null ? CKC_NAMES[pred] ?? `Stage ${pred}` : "—";
  const currName = current != null ? CKC_NAMES[current] ?? `Stage ${current}` : "—";

  // Bar per stage from recent prediction frequency — shows which
  // stage the transformer projects most often. Histogram of
  // `transformerPredCkc` across recent events.
  const histogram = useMemo(() => {
    const counts = new Array(8).fill(0) as number[];
    for (const e of events.slice(0, 80)) {
      const v = e.transformerPredCkc;
      if (v != null && v >= 0 && v < 8) counts[v]++;
    }
    return counts;
  }, [events]);
  const histMax = Math.max(1, ...histogram);

  return (
    <PanelShell
      title="Transformer"
      subtitle="CKC next-step predictor"
      accent="emerald"
      active={active}
      footer={
        latest
          ? `${latest.alertId.slice(0, 12)}… · ${fmtAgo(latest.occurredAt)}`
          : "Idle"
      }
    >
      <div className="space-y-3">
        <div className="flex items-end justify-between">
          <HeroNumber
            value={pred == null ? "—" : String(pred)}
            unit={predName}
            tone={pred != null && pred >= 5 ? "high" : pred != null && pred >= 3 ? "mid" : "default"}
          />
          <div className="text-right">
            <p className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)]">conf</p>
            <p className="text-[14px] font-bold text-emerald-400 font-mono">
              {conf == null ? "—" : `${Math.round(conf * 100)}%`}
            </p>
          </div>
        </div>
        <div className="flex items-end gap-1 h-8">
          {histogram.map((c, i) => (
            <div
              key={i}
              className={`flex-1 rounded-sm transition-all ${
                pred === i ? "bg-emerald-500" : "bg-emerald-500/30"
              }`}
              style={{ height: `${(c / histMax) * 100}%` }}
              title={`Stage ${i} (${CKC_NAMES[i]}): ${c}`}
            />
          ))}
        </div>
        <p className="text-[10px] text-[var(--strix-text-muted)] flex items-center gap-1">
          <span>now:</span>
          <span className="text-[var(--strix-text)] font-mono">{currName}</span>
          <span>→</span>
          <span className="text-emerald-400 font-mono">{predName}</span>
        </p>
      </div>
    </PanelShell>
  );
}

// ---------------------------------------------------------------- DQN panel

const DQN_ACTIONS = ["MONITOR", "LOW_ALERT", "ESCALATE", "ISOLATE_HOST", "BLOCK_USER_IP"];
const DQN_ACTION_TONES: Record<string, string> = {
  MONITOR: "text-[var(--strix-text-muted)]",
  LOW_ALERT: "text-amber-400",
  ESCALATE: "text-rose-400",
  ISOLATE_HOST: "text-rose-500",
  BLOCK_USER_IP: "text-rose-600",
};

export function DqnPanel({
  events,
  active,
}: {
  events: LiveFeedEvent[];
  active: boolean;
}) {
  const latest = events[0];
  const action = latest?.dqnAction ?? null;
  const actionName = latest?.dqnActionName ?? null;
  const q = latest?.qValues ?? [];
  const qMax = q.length > 0 ? Math.max(...q.map(Math.abs)) : 1;

  // Action distribution (last 40 events)
  const dist = useMemo(() => {
    const counts = new Array(5).fill(0) as number[];
    for (const e of events.slice(0, 40)) {
      if (e.dqnAction != null && e.dqnAction >= 0 && e.dqnAction < 5) {
        counts[e.dqnAction]++;
      }
    }
    return counts;
  }, [events]);
  const distMax = Math.max(1, ...dist);

  const isIntervention = action != null && action >= 2;

  return (
    <PanelShell
      title="STRIX Agent"
      subtitle="DQN policy · response action selector"
      accent="rose"
      active={active}
      footer={
        latest
          ? `${latest.alertId.slice(0, 12)}… · ${fmtAgo(latest.occurredAt)}`
          : "Idle"
      }
    >
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)]">latest action</p>
            <p className={`text-[18px] font-bold leading-tight font-[family-name:var(--font-space-grotesk)] ${
              actionName ? DQN_ACTION_TONES[actionName] ?? "text-[var(--strix-text)]" : "text-[var(--strix-text-muted)]"
            }`}>
              {actionName ?? "—"}
            </p>
          </div>
          {isIntervention && (
            <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30">
              intervention
            </span>
          )}
        </div>
        {/* Q-values bars (vertical) */}
        <div>
          <p className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)] mb-1">q-values</p>
          <div className="flex items-end gap-1 h-12">
            {DQN_ACTIONS.map((name, i) => {
              const v = q[i] ?? 0;
              const h = qMax > 0 ? Math.max(2, (Math.abs(v) / qMax) * 100) : 2;
              const winning = action === i;
              return (
                <div key={name} className="flex-1 flex flex-col items-center justify-end">
                  <div
                    className={`w-full rounded-sm transition-all ${
                      winning ? "bg-rose-500" : "bg-rose-500/30"
                    }`}
                    style={{ height: `${h}%` }}
                    title={`${name}: ${v.toFixed(3)}`}
                  />
                </div>
              );
            })}
          </div>
          <div className="flex gap-1 mt-1">
            {DQN_ACTIONS.map((name, i) => (
              <span
                key={name}
                className={`flex-1 text-center text-[7px] uppercase tracking-tight truncate ${
                  action === i ? "text-rose-400 font-bold" : "text-[var(--strix-text-muted)]"
                }`}
                title={name}
              >
                {name.split("_")[0]}
              </span>
            ))}
          </div>
        </div>
        {/* Distribution mini-bars */}
        <div className="flex items-center gap-2 text-[9px]">
          <span className="uppercase tracking-wider text-[var(--strix-text-muted)] w-12">last 40</span>
          {DQN_ACTIONS.map((name, i) => (
            <div key={name} className="flex-1 h-2 rounded-full bg-[var(--strix-bg-deep)] overflow-hidden">
              <div
                className="h-full bg-rose-400/60"
                style={{ width: `${(dist[i] / distMax) * 100}%` }}
                title={`${name}: ${dist[i]}`}
              />
            </div>
          ))}
        </div>
      </div>
    </PanelShell>
  );
}
