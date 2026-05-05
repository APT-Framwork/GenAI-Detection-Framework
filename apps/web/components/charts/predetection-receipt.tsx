// -----------------------------------------------------------------------------
// predetection-receipt.tsx — credibility artefact for the agent's predetection.
//
// Two variants (decided per-mount via `variant` prop):
//   * "inline" — full-width card under the kill-chain panel. Each predetected
//     host gets a row showing stage caught, last technique, elapsed time,
//     DQN action + confidence, and a stage-7 strikethrough ("would have
//     happened next").
//   * "rail" — vertical stack of compact toast cards in a right-rail.
//     Same data, smaller footprint, slides in on latch.
//
// Reads from the shared predetection store (lib/predetection-store.ts). The
// store is populated by rl-kill-chain.tsx the first time a host's RL frame
// shows action ≥ ESCALATE while chain_max_ckc_stage ≤ 6. Once latched, the
// row is sticky — it does not auto-dismiss, because the whole point of
// the panel is to be a persistent jury-facing proof.
// -----------------------------------------------------------------------------

"use client";

import { useMemo } from "react";
import { ShieldCheck, Zap, Clock, Crosshair, Brain, type LucideIcon } from "lucide-react";

import { usePredetections, type Predetection } from "@/lib/predetection-store";
import { HoverHelp } from "@/components/ui/hover-help";
import { cn } from "@/lib/utils";

const STAGE_LABELS = [
  "Recon",
  "Weapon",
  "Delivery",
  "Exploit",
  "Install",
  "C2",
  "Action",
];

interface PredetectionReceiptProps {
  variant: "inline" | "rail";
  className?: string;
}

export function PredetectionReceipt({ variant, className }: PredetectionReceiptProps) {
  const all = usePredetections();
  const list = useMemo(
    () => Array.from(all.values()).sort((a, b) => b.latchedAt - a.latchedAt),
    [all],
  );

  if (variant === "rail") return <RailVariant list={list} className={className} />;
  return <InlineVariant list={list} className={className} />;
}

// ---------------------------------------------------------------------------
// Inline variant — full-width card under the kill-chain panel
// ---------------------------------------------------------------------------

function InlineVariant({
  list,
  className,
}: {
  list: Predetection[];
  className?: string;
}) {
  if (list.length === 0) {
    return (
      <div
        className={cn(
          "rounded-2xl border border-dashed border-emerald-500/30 bg-emerald-500/[0.02] p-5 text-center",
          className,
        )}
      >
        <ShieldCheck size={20} className="mx-auto mb-2 text-emerald-500/60" />
        <p className="text-[11px] uppercase tracking-wider text-emerald-600/70 font-semibold">
          Awaiting predetection
        </p>
        <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-1 max-w-md mx-auto">
          Receipt populates the moment the RL agent intervenes (action ≥
          ESCALATE) before any chain reaches stage 7. Benign-only hosts will
          stay quiet — that&apos;s the agent&apos;s correct behaviour.
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/[0.05] to-transparent p-5",
        className,
      )}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ShieldCheck size={18} className="text-emerald-500" />
          <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
            Predetection Receipts
          </h3>
          <HoverHelp
            title="What's a receipt?"
            body={
              <>
                One row per host where the agent fired{" "}
                <strong>ESCALATE</strong> before the chain hit stage 7.
                Sticky — does not auto-dismiss; the panel exists to be a
                persistent, jury-facing proof.
              </>
            }
          >
            <span className="text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400 font-semibold">
              {list.length} caught
            </span>
          </HoverHelp>
        </div>
        <HoverHelp
          title="Success criterion"
          body={
            <>
              The paper&apos;s <em>predetection success</em> threshold:
              caught at stage ≤ 6. Stages 5–6 (<code>Install</code> /{" "}
              <code>C2</code>) are the <em>critical max</em> — anywhere
              earlier is even better.
            </>
          }
          align="end"
        >
          <span className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            stage ≤ 6 = success
          </span>
        </HoverHelp>
      </div>

      <div className="grid grid-cols-1 gap-3">
        {list.map((p) => (
          <InlineRow key={p.hostId} p={p} />
        ))}
      </div>
    </div>
  );
}

function InlineRow({ p }: { p: Predetection }) {
  const stageLabel = STAGE_LABELS[Math.max(0, p.stage - 1)] ?? "?";
  const elapsedSec = (p.elapsedMs / 1000).toFixed(2);
  const wallElapsedLabel =
    p.wallElapsedMs != null
      ? p.wallElapsedMs < 1000
        ? `${Math.round(p.wallElapsedMs)}ms`
        : `${(p.wallElapsedMs / 1000).toFixed(1)}s`
      : null;
  const tier = p.isCritical ? "CRITICAL CATCH" : "EARLY CATCH";
  const tierColor = p.isCritical ? "text-amber-500" : "text-emerald-500";

  return (
    <div className="rounded-xl border border-emerald-500/25 bg-[var(--strix-bg-card)] dark:bg-[var(--strix-bg-surface)] p-4 animate-slide-up-in">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-[12px] font-bold text-[#00343d] dark:text-[var(--strix-text)] truncate">
            {p.victimLabel ?? p.hostId}
          </span>
          <HoverHelp
            title={tier === "CRITICAL CATCH" ? "Critical catch" : "Early catch"}
            body={
              tier === "CRITICAL CATCH" ? (
                <>
                  The agent intervened at stage{" "}
                  <strong>{p.stage}</strong> — within the paper&apos;s
                  &quot;critical max&quot; (5–6: <code>Install</code> /{" "}
                  <code>C2</code>). The window to prevent stage 7 was
                  narrow but the agent caught it.
                </>
              ) : (
                <>
                  Intervened at stage <strong>{p.stage}</strong> — well
                  before the critical band (Install/C2). The earliest
                  catches are the cleanest.
                </>
              )
            }
          >
            <span className={cn("text-[9px] font-semibold uppercase tracking-wider", tierColor)}>
              · {tier}
            </span>
          </HoverHelp>
        </div>
        <HoverHelp
          title="Agent action"
          body={
            <>
              The DQN&apos;s recommended action at the moment of latch (
              <strong>{p.actionName || `action ${p.action}`}</strong>).
              Anything ≥ <code>ESCALATE</code> (action 2) qualifies as an
              intervention. In the lab this is a recommendation only —
              nothing is actually executed against the host.
            </>
          }
          align="end"
        >
          <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10">
            ⛨ {p.actionName || "INTERVENED"}
          </span>
        </HoverHelp>
      </div>

      {/* Mini-stat grid */}
      <div className="grid grid-cols-4 gap-2 mb-3">
        <Stat
          icon={Crosshair}
          label="Caught at"
          value={`${stageLabel}`}
          sub={`stage ${p.stage}/7`}
          help={
            <>
              Deepest CKC stage observed before the agent latched. Comes
              from the running max of three signals: the Transformer&apos;s
              own prediction, the Wazuh→MITRE→CKC mapping for each event,
              and the chain&apos;s prior max stage.
            </>
          }
        />
        <Stat
          icon={Clock}
          label="Time to detect"
          value={`${elapsedSec}s`}
          sub={wallElapsedLabel ? `wall ${wallElapsedLabel}` : "event-time"}
          help={
            <>
              <strong>Event-time TTI</strong> ({elapsedSec}s) — gap between
              two Wazuh <code>occurred_at</code> timestamps: the alert that
              opened the chain → the alert that triggered ESCALATE.
              {wallElapsedLabel != null && (
                <>
                  <br />
                  <strong>Wall-clock TTI</strong> ({wallElapsedLabel}) —
                  server clock at decide minus server clock at chain-open.
                  Captures pipeline latency end-to-end.
                </>
              )}
            </>
          }
        />
        <Stat
          icon={Brain}
          label="Transformer conf."
          value={`${(p.confidence * 100).toFixed(0)}%`}
          sub={`DQN action ${p.action}`}
          help={
            <>
              Transformer softmax max over the 8-class CKC head at latch.
              <br />
              <em>Note:</em> this is the upstream classifier&apos;s
              confidence, <strong>not</strong> the DQN&apos;s — the DQN
              outputs Q-values, not probabilities. Action{" "}
              <code>{p.action}</code> = <code>{p.actionName}</code>.
            </>
          }
        />
        <Stat
          icon={Zap}
          label="Last technique"
          value={p.technique ?? "—"}
          sub={p.tactic ?? "no tactic tag"}
          help={
            <>
              Most recent MITRE technique observed for this host before
              latch. The latch frame itself often has no MITRE tag (DQN
              fires on a non-tagged downstream event), so we backfill from
              the last tagged frame in the chain.
            </>
          }
        />
      </div>

      {/* Stage strip — emerald up to caught, strikethrough red beyond */}
      <HoverHelp
        title="Kill-chain stage strip"
        body={
          <>
            <strong>Filled emerald</strong>: stages reached before the
            agent intervened. <strong>Bright emerald</strong>: the latch
            stage. <strong>Dashed red strikethrough</strong>: stages the
            chain would have walked through next, prevented by the
            ESCALATE.
          </>
        }
        block
      >
        <div className="flex items-center gap-1 w-full">
          {STAGE_LABELS.map((label, i) => {
            const stageIdx = i + 1;
            const isCaught = stageIdx === p.stage;
            const isReached = stageIdx <= p.stage;
            const isPrevented = stageIdx > p.stage;
            return (
              <div
                key={label}
                className={cn(
                  "flex-1 rounded-md py-1.5 text-center text-[9px] font-mono font-semibold",
                  isCaught && "bg-emerald-500 text-white shadow-[0_0_0_2px_rgba(16,185,129,0.3)]",
                  isReached && !isCaught && "bg-emerald-500/30 text-emerald-700 dark:text-emerald-300",
                  isPrevented && "bg-rose-500/[0.08] text-rose-500/55 line-through border border-dashed border-rose-500/30",
                )}
              >
                {label}
              </div>
            );
          })}
        </div>
      </HoverHelp>

      <div className="mt-2 text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] flex items-center justify-between">
        <span>
          Agent recommendation: <strong className="text-emerald-600 dark:text-emerald-400">{p.actionName || `action ${p.action}`}</strong> — chain frozen client-side.
        </span>
        <HoverHelp
          title="Stages prevented"
          body={
            <>
              Counterfactual stages <code>{p.stage + 1}</code>–<code>7</code>{" "}
              never occurred because the agent latched at stage{" "}
              <strong>{p.stage}</strong>. In a real engagement those would
              have been C2 establishment and final actions on objective.
            </>
          }
          align="end"
        >
          <span className="text-rose-500/70">stages {p.stage + 1}-7 prevented</span>
        </HoverHelp>
      </div>
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  sub,
  help,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  sub: string;
  /** Optional rich body shown on hover. When provided, the whole tile is
   *  interactive (cursor-help) and tabbable. */
  help?: React.ReactNode;
}) {
  const tile = (
    <div className="rounded-lg border border-[rgba(128,182,195,0.18)] dark:border-[var(--strix-border)] px-2 py-1.5 w-full">
      <div className="flex items-center gap-1 text-[8px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-0.5">
        <Icon size={9} />
        {label}
      </div>
      <div className="text-[12px] font-bold font-mono text-[#00343d] dark:text-[var(--strix-text)] truncate">
        {value}
      </div>
      <div className="text-[8px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] truncate">
        {sub}
      </div>
    </div>
  );
  if (!help) return tile;
  return (
    <HoverHelp title={label} body={help} block>
      {tile}
    </HoverHelp>
  );
}

// ---------------------------------------------------------------------------
// Rail variant — sticky right-rail compact toast stack
// ---------------------------------------------------------------------------

function RailVariant({
  list,
  className,
}: {
  list: Predetection[];
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2 w-[280px]", className)}>
      <div className="flex items-center gap-2 px-1 mb-1">
        <ShieldCheck size={14} className="text-emerald-500" />
        <span className="text-[10px] uppercase tracking-wider font-bold text-emerald-600 dark:text-emerald-400">
          Predetection Receipts
        </span>
        <span className="text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] ml-auto">
          {list.length}
        </span>
      </div>

      {list.length === 0 && (
        <div className="rounded-xl border border-dashed border-emerald-500/25 bg-emerald-500/[0.02] p-3 text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] text-center">
          waiting for the agent…
        </div>
      )}

      {list.map((p) => (
        <RailCard key={p.hostId} p={p} />
      ))}
    </div>
  );
}

function RailCard({ p }: { p: Predetection }) {
  const stageLabel = STAGE_LABELS[Math.max(0, p.stage - 1)] ?? "?";
  const elapsedSec = (p.elapsedMs / 1000).toFixed(2);
  return (
    <div className="rounded-xl border border-emerald-500/30 bg-[var(--strix-bg-card)] dark:bg-[var(--strix-bg-surface)] p-3 animate-slide-up-in shadow-[0_0_0_1px_rgba(16,185,129,0.12)_inset]">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[11px] font-bold text-emerald-600 dark:text-emerald-400 truncate">
          ⛨ {p.victimLabel ?? p.hostId}
        </span>
        <span className="text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {elapsedSec}s
        </span>
      </div>
      <div className="text-[10px] font-mono text-[#00343d] dark:text-[var(--strix-text)]">
        caught at <strong className="text-emerald-600 dark:text-emerald-400">{stageLabel}</strong>{" "}
        <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)]">(stage {p.stage}/7)</span>
      </div>
      {p.technique && (
        <div className="text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-1 truncate">
          tech {p.technique}
          {p.tactic ? ` · ${p.tactic}` : ""}
        </div>
      )}
      <div className="mt-2 grid grid-cols-7 gap-0.5">
        {STAGE_LABELS.map((_, i) => {
          const stageIdx = i + 1;
          const isCaught = stageIdx === p.stage;
          const isReached = stageIdx <= p.stage;
          const isPrevented = stageIdx > p.stage;
          return (
            <div
              key={i}
              className={cn(
                "h-1.5 rounded-sm",
                isCaught && "bg-emerald-500",
                isReached && !isCaught && "bg-emerald-500/40",
                isPrevented && "bg-rose-500/20 border border-rose-500/30",
              )}
            />
          );
        })}
      </div>
      <div className="mt-1.5 text-[8px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] flex justify-between">
        <span>{p.actionName || `act ${p.action}`}</span>
        <span>{(p.confidence * 100).toFixed(0)}% conf</span>
      </div>
    </div>
  );
}
