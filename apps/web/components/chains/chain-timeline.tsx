// chain-timeline.tsx — unified case timeline for an attack chain.
//
// Merges three streams into one chronological log:
//   1. CKC stage transitions  (from /chains/{id}/ckc-progression)
//   2. DQN action decisions    (per-stage actions from the same source)
//   3. Operator audit events   (triage, tag, tlp, note, attribution)
//
// This is the "case timeline" view defined by IR platforms — analyst
// reads one stream instead of switching between three.

"use client";

import { useMemo } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Crosshair,
  FileText,
  Layers,
  ShieldAlert,
  Tag as TagIcon,
  Target,
  Zap,
  X,
} from "lucide-react";

import { useChainActivity, type ActivityEvent } from "@/lib/api/chains";
import { useCkcProgression, type CkcProgressionStep } from "@/lib/api/analysis";
import { cn } from "@/lib/utils";

interface MergedItem {
  id: string;
  at: string;
  Icon: typeof ArrowRight;
  iconCls: string;
  label: string;
  detail?: string;
  actor?: string;        // "system" or user email
  group: "engine" | "operator";  // colour the timeline rail
}

function fmtAgo(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = (Date.now() - t) / 1000;
  if (diff < 60) return `${Math.max(0, Math.floor(diff))}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function fmtClock(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-GB", { hour12: false });
  } catch {
    return "—";
  }
}

function fromStage(s: CkcProgressionStep): MergedItem[] {
  const out: MergedItem[] = [
    {
      id: `stage-${s.ckcStage}-${s.enteredAt}`,
      at: s.enteredAt,
      Icon: Layers,
      iconCls: stageColour(s.ckcStage),
      label: `Stage ${s.ckcStage} · ${s.ckcStageName}`,
      detail: "engine advanced the chain to this kill-chain stage",
      actor: "engine",
      group: "engine",
    },
  ];
  if (s.dqnAction && s.actionedAt) {
    out.push({
      id: `dqn-${s.ckcStage}-${s.actionedAt}`,
      at: s.actionedAt,
      Icon: Zap,
      iconCls: dqnColour(s.dqnAction),
      label: `STRIX action: ${s.dqnAction}`,
      detail: `STRIX agent's recommendation at stage ${s.ckcStage}`,
      actor: "engine",
      group: "engine",
    });
  }
  return out;
}

function stageColour(stage: number): string {
  if (stage >= 6) return "text-rose-400";
  if (stage >= 4) return "text-orange-400";
  if (stage >= 2) return "text-amber-400";
  return "text-strix-cyan";
}

function dqnColour(action: string): string {
  switch (action) {
    case "BLOCK_USER_IP": return "text-rose-600";
    case "ISOLATE_HOST":  return "text-rose-500";
    case "ESCALATE":      return "text-rose-400";
    case "LOW_ALERT":     return "text-amber-400";
    default:              return "text-[var(--strix-text-muted)]";
  }
}

function fromActivity(ev: ActivityEvent): MergedItem {
  switch (ev.kind) {
    case "triage":
      return {
        id: `act-${ev.auditId}`,
        at: ev.at,
        Icon: ArrowRight,
        iconCls: "text-strix-cyan",
        label: ev.fromStatus
          ? `Triage: ${ev.fromStatus} → ${ev.payload}`
          : `Triage: ${ev.payload}`,
        detail: ev.note ?? undefined,
        actor: ev.userEmail ?? "system",
        group: ev.userEmail ? "operator" : "engine",
      };
    case "tag.added":
      return {
        id: `act-${ev.auditId}`,
        at: ev.at,
        Icon: TagIcon,
        iconCls: "text-emerald-400",
        label: `Tag added · ${ev.payload}`,
        actor: ev.userEmail ?? "system",
        group: "operator",
      };
    case "tag.removed":
      return {
        id: `act-${ev.auditId}`,
        at: ev.at,
        Icon: X,
        iconCls: "text-rose-400",
        label: `Tag removed · ${ev.payload}`,
        actor: ev.userEmail ?? "system",
        group: "operator",
      };
    case "tlp":
      return {
        id: `act-${ev.auditId}`,
        at: ev.at,
        Icon: ShieldAlert,
        iconCls: "text-amber-400",
        label: `TLP · ${ev.payload}`,
        actor: ev.userEmail ?? "system",
        group: "operator",
      };
    case "note.added":
      return {
        id: `act-${ev.auditId}`,
        at: ev.at,
        Icon: FileText,
        iconCls: "text-[var(--strix-text-muted)]",
        label: "Note added",
        detail: ev.note ?? undefined,
        actor: ev.userEmail ?? "system",
        group: "operator",
      };
    case "attribution":
      return {
        id: `act-${ev.auditId}`,
        at: ev.at,
        Icon: Crosshair,
        iconCls: "text-rose-400",
        label: `Attribution · ${ev.payload}`,
        detail: ev.note ?? undefined,
        actor: ev.userEmail ?? "system",
        group: "engine",
      };
    default:
      return {
        id: `act-${ev.auditId}`,
        at: ev.at,
        Icon: AlertTriangle,
        iconCls: "text-[var(--strix-text-muted)]",
        label: `${ev.kind}: ${ev.payload ?? ev.toStatus}`,
        actor: ev.userEmail ?? "system",
        group: "operator",
      };
  }
}

export function ChainTimeline({ chainId }: { chainId: string }) {
  const activity = useChainActivity(chainId);
  const progression = useCkcProgression(chainId);

  const items = useMemo<MergedItem[]>(() => {
    const merged: MergedItem[] = [];
    for (const step of progression.data?.stages ?? []) {
      merged.push(...fromStage(step));
    }
    for (const ev of activity.data?.items ?? []) {
      merged.push(fromActivity(ev));
    }
    return merged.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  }, [progression.data, activity.data]);

  const isLoading = activity.isLoading && progression.isLoading;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Target className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
        <h3 className="text-sm font-bold text-[var(--strix-text)]">Case timeline</h3>
        <span className="text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider">
          engine + operator
        </span>
        <span className="ml-auto text-[10px] text-[var(--strix-text-muted)] tabular-nums">
          {items.length} {items.length === 1 ? "event" : "events"}
        </span>
      </div>
      {isLoading && items.length === 0 ? (
        <p className="text-[11px] text-[var(--strix-text-muted)] italic">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-[11px] text-[var(--strix-text-muted)] italic">
          No events yet — engine + operator events will appear here.
        </p>
      ) : (
        <ol className="relative space-y-2.5 max-h-[420px] overflow-y-auto pr-1">
          {/* Rail */}
          <div className="absolute left-[7px] top-1 bottom-1 w-px bg-[var(--strix-border)]" />
          {items.map((it) => (
            <li key={it.id} className="relative flex items-start gap-2.5 pl-1">
              <span
                className={cn(
                  "relative z-10 mt-0.5 h-3.5 w-3.5 shrink-0 rounded-full flex items-center justify-center",
                  it.group === "engine"
                    ? "bg-[var(--strix-bg-card)] border border-strix-cyan/40"
                    : "bg-[var(--strix-bg-card)] border border-emerald-500/40",
                )}
              >
                <it.Icon className={cn("h-2.5 w-2.5", it.iconCls)} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[12px] text-[var(--strix-text)] leading-tight">
                  {it.label}
                </p>
                <p className="text-[10px] text-[var(--strix-text-muted)] flex items-center gap-2 mt-0.5">
                  <span className="font-mono">{fmtClock(it.at)}</span>
                  <span>·</span>
                  <span>{fmtAgo(it.at)}</span>
                  {it.actor && (
                    <>
                      <span>·</span>
                      <span className="truncate">{it.actor}</span>
                    </>
                  )}
                </p>
                {it.detail && (
                  <p className="text-[10px] text-[var(--strix-text-muted)] italic mt-0.5">
                    {it.detail}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
