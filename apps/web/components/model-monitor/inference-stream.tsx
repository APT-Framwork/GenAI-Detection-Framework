// inference-stream.tsx — compact firehose table for /ai-engine.
//
// Each row is one verdict. Columns: time, host, CKC stage, AE score,
// VAE prob, GNN risk, Transformer pred+conf, DQN action. The whole
// row is colour-tinted by ckcStage so the table reads at a glance as
// a heat-coded stream.

"use client";

import { useMemo } from "react";
import Link from "next/link";
import type { LiveFeedEvent } from "@/lib/api/live-feed";

function fmtClock(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-GB", { hour12: false });
  } catch {
    return "—";
  }
}

function stageBg(stage: number): string {
  // Single-class string per Tailwind safelist concerns; we use rgba inline.
  return [
    "bg-transparent",                  // 0 BENIGN
    "bg-amber-500/[0.04]",             // 1 Recon
    "bg-amber-500/[0.07]",             // 2 Weaponization
    "bg-amber-500/[0.10]",             // 3 Delivery
    "bg-orange-500/[0.10]",            // 4 Exploitation
    "bg-rose-500/[0.10]",              // 5 Installation
    "bg-rose-500/[0.15]",              // 6 C2
    "bg-rose-600/[0.20]",              // 7 Actions
  ][Math.max(0, Math.min(7, stage))];
}

function stageBadge(stage: number, name: string): string {
  if (stage === 0) return "text-[var(--strix-text-muted)]";
  if (stage <= 2) return "text-amber-400";
  if (stage <= 4) return "text-orange-400";
  return "text-rose-400";
}

function numFmt(v: number | null, digits = 2): string {
  return v == null ? "—" : v.toFixed(digits);
}

function pctFmt(v: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

const ACTION_CLS: Record<string, string> = {
  MONITOR: "text-[var(--strix-text-muted)]",
  LOW_ALERT: "text-amber-400",
  ESCALATE: "text-rose-400 font-bold",
  ISOLATE_HOST: "text-rose-500 font-bold",
  BLOCK_USER_IP: "text-rose-600 font-bold",
};

export function InferenceStream({
  events,
}: {
  events: LiveFeedEvent[];
}) {
  // Cap to keep the DOM cheap; SSE buffer is larger so the panels can
  // show longer-window stats.
  const rows = useMemo(() => events.slice(0, 30), [events]);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] font-mono">
        <thead>
          <tr className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)] border-b border-[var(--strix-border)]">
            <th className="text-left py-2 px-2">Time</th>
            <th className="text-left py-2 px-2">Host</th>
            <th className="text-left py-2 px-2">CKC</th>
            <th className="text-right py-2 px-2">AE</th>
            <th className="text-right py-2 px-2">VAE</th>
            <th className="text-right py-2 px-2">GNN</th>
            <th className="text-right py-2 px-2">TX pred</th>
            <th className="text-right py-2 px-2">TX conf</th>
            <th className="text-left py-2 px-2">STRIX</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={9} className="py-8 text-center text-[var(--strix-text-muted)] italic">
                Awaiting inferences… fire a sim to populate.
              </td>
            </tr>
          ) : (
            rows.map((e, idx) => {
              const isLatest = idx === 0;
              return (
                <tr
                  key={e.alertId + idx}
                  className={`border-b border-[var(--strix-border)]/40 hover:bg-[var(--strix-bg-surface)] ${
                    stageBg(e.ckcStage)
                  } ${isLatest ? "animate-[fade_0.6s_ease-out]" : ""}`}
                >
                  <td className="py-1.5 px-2 text-[var(--strix-text-muted)]">{fmtClock(e.occurredAt)}</td>
                  <td className="py-1.5 px-2 text-[var(--strix-text)] truncate max-w-[80px]">
                    {e.agentId ?? "—"}
                  </td>
                  <td className={`py-1.5 px-2 ${stageBadge(e.ckcStage, e.ckcStageName)}`}>
                    <span className="font-bold">{e.ckcStage}</span>
                    <span className="ml-1 text-[9px] uppercase">{e.ckcStageName.slice(0, 5)}</span>
                  </td>
                  <td className="py-1.5 px-2 text-right text-strix-cyan">{numFmt(e.aeAnomalyScore)}</td>
                  <td className="py-1.5 px-2 text-right text-purple-400">{pctFmt(e.vaeMaliciousProb)}</td>
                  <td className="py-1.5 px-2 text-right text-amber-400">{numFmt(e.gnnNodeRisk)}</td>
                  <td className="py-1.5 px-2 text-right text-emerald-400">
                    {e.transformerPredCkc ?? "—"}
                  </td>
                  <td className="py-1.5 px-2 text-right text-emerald-400">{pctFmt(e.transformerConfidence)}</td>
                  <td className={`py-1.5 px-2 ${ACTION_CLS[e.dqnActionName ?? ""] ?? "text-[var(--strix-text-muted)]"}`}>
                    {e.dqnActionName ?? "—"}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
