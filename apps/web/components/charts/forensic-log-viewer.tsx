// -----------------------------------------------------------------------------
// forensic-log-viewer.tsx (Phase 4 — terminal-style live log box).
//
// Two modes:
//   * Live mode (default): subscribes to `useLogStream(["raw_log"])` and shows
//     the 4–5 most recent events with a slide-up animation. Pause/resume button
//     freezes RENDER, not the stream — the WebSocket keeps appending into the
//     ring buffer in `lib/api/ws.ts` so resume catches up to the freshest tail.
//   * Legacy mode: pass `logs={…}` to render a static list (used by the
//     attack-analysis chain page where logs come from a per-chain query).
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, Terminal } from "lucide-react";

import {
  severityColors,
  severityFromCkcStage,
  severityFromRisk,
  type Severity,
} from "@/lib/design-tokens";
import {
  useLogStream,
  useLogStreamConnection,
  type RawLogPayload,
} from "@/lib/api/ws";
import { cn } from "@/lib/utils";
import type { LogEntry } from "@/types";

// Full forensic envelope passed to Export JSON / CSV — keeps the raw
// payload alongside the rendered fields so the artefact a jury or auditor
// downloads is the *exact* WS frame the dashboard saw, not a UI-projected
// summary.
interface ForensicExportRow {
  receivedAt: string;
  occurredAt: string;
  alertId: string;
  agentId: string;
  chainId: string;
  ruleId: string;
  ckcStage: string;
  ckcStageName: string;
  aeAnomalyScore: string;
  vaeMaliciousProb: string;
  gnnNodeRisk: string;
  dqnAction: string;
  dqnActionName: string;
  mitreTactics: string;
  mitreTechniques: string;
  description: string;
  fullLog: string;
}

interface ForensicLogViewerProps {
  /**
   * Optional static logs. When provided, the viewer renders these (legacy
   * mode for the attack-analysis chain page). When omitted, it binds to the
   * live `raw_log` WebSocket stream.
   */
  logs?: LogEntry[];
  /** How many recent lines to show in live mode. Plan §4-Phase-4: 4–5. */
  tailLines?: number;
  className?: string;
}

interface DisplayLine {
  key: string;
  timestamp: string;
  level: string;
  severity: Severity;
  message: string;
}

const FALLBACK_LEVEL_COLORS: Record<string, string> = {
  AUTH: "text-gray-400",
  WARN: "text-amber-400",
  ERROR: "text-red-400",
  INFO: "text-blue-400",
  ALERT: "text-orange-400",
  BLOCK: "text-red-500",
  STRIX_AI: "text-cyan-400",
  NOTICE: "text-emerald-400",
  PROCESS: "text-purple-400",
  SUCCESS: "text-emerald-400",
  EXEC: "text-amber-400",
  NET: "text-blue-400",
};

function formatTime(iso: string | undefined): string {
  if (!iso) return "--:--:--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(11, 19) || iso;
  return d.toISOString().slice(11, 19);
}

// Severity rank — higher = more severe. Used to combine signals from
// multiple models so a benign Transformer prediction can't override an
// ESCALATE/ISOLATE intervention or a high GNN risk.
const SEV_RANK: Record<Severity, number> = {
  benign: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};
function maxSeverity(...sevs: Severity[]): Severity {
  return sevs.reduce((acc, s) => (SEV_RANK[s] > SEV_RANK[acc] ? s : acc), "benign");
}
// DqnAction integers (matches apps/api/.../core/enums/dqn.py).
//   0=MONITOR, 1=LOW_ALERT, 2=ESCALATE, 3=ISOLATE_HOST, 4=BLOCK_USER_IP
function severityFromDqnAction(action: number): Severity {
  if (action >= 4) return "critical";
  if (action >= 3) return "high";
  if (action >= 2) return "high";
  if (action >= 1) return "medium";
  return "benign";
}

function payloadToLine(p: RawLogPayload, ts: string): DisplayLine {
  const stage = typeof p.ckcStage === "number" ? p.ckcStage : 0;
  // Combine signals — Transformer's CKC alone misclassifies many real-attack
  // events as benign (it was trained on a Wazuh distribution that doesn't
  // match the live audit firehose 1:1). Take the max of CKC, DQN action,
  // and GNN node risk so an ESCALATE/ISOLATE or high node-risk forces the
  // line into the appropriate colour band.
  const ckcSev = severityFromCkcStage(stage);
  const action = typeof p.dqnAction === "number" ? p.dqnAction : 0;
  const dqnSev = severityFromDqnAction(action);
  const risk = typeof p.gnnNodeRisk === "number" ? p.gnnNodeRisk : 0;
  const riskSev = severityFromRisk(risk);
  const severity = maxSeverity(ckcSev, dqnSev, riskSev);
  // Prefer the DQN action label when the agent has actually intervened —
  // that's the most actionable thing for an analyst to read.
  const level = (
    action >= 2 && p.dqnActionName
      ? p.dqnActionName
      : p.ckcStageName ?? p.dqnActionName ?? "EVENT"
  ).toUpperCase();
  const agent = p.agentId ?? p.agent_id ?? "—";
  const mitre = (p.mitreTechniques ?? []).slice(0, 3).join(",");
  const actionStr = p.dqnActionName ? ` action=${p.dqnActionName}` : "";
  const riskStr = typeof p.gnnNodeRisk === "number" ? ` risk=${p.gnnNodeRisk.toFixed(2)}` : "";
  const message = `agent=${agent}${actionStr}${riskStr}${mitre ? ` mitre=${mitre}` : ""}`;
  return {
    key: `${p.alertId ?? p.alert_id ?? ts}-${ts}`,
    timestamp: formatTime(p.occurredAt ?? ts),
    level,
    severity,
    message,
  };
}

export function ForensicLogViewer({ logs, tailLines = 10, className }: ForensicLogViewerProps) {
  const isLive = logs === undefined;

  // Live mode state.
  const live = useLogStream(["raw_log"]);
  const conn = useLogStreamConnection();
  const [paused, setPaused] = useState(false);
  const [showAll, setShowAll] = useState(false);

  // When paused, freeze the snapshot reference so re-renders triggered by
  // unrelated state (parent re-renders, the 1Hz tick from the status hook)
  // don't pull a fresher slice.
  const frozenRef = useRef<DisplayLine[] | null>(null);

  const liveLines: DisplayLine[] = useMemo(() => {
    if (!isLive) return [];
    if (paused && frozenRef.current) return frozenRef.current;
    const buf = live.frames.raw_log ?? [];
    // showAll: surface the entire retained ring buffer (up to ~500 frames)
    // collapsed: keep the original tail-N behaviour for the dashboard view.
    const tail = (showAll ? buf.slice() : buf.slice(-tailLines)).reverse();
    const lines = tail.map((f) => payloadToLine(f.payload, f.ts));
    frozenRef.current = lines;
    return lines;
    // live.seq.raw_log advances on every new frame — that's our render trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLive, paused, tailLines, showAll, live.seq.raw_log]);

  // Buffer count (newest-first, full ring) used by Export buttons.
  const retainedCount = isLive ? (live.frames.raw_log?.length ?? 0) : 0;

  // Capture the snapshot at the moment of pause so resume picks up cleanly.
  useEffect(() => {
    if (paused && isLive) frozenRef.current = liveLines;
  }, [paused, isLive, liveLines]);

  // Legacy mode: project LogEntry[] into DisplayLine[].
  const legacyLines: DisplayLine[] = useMemo(() => {
    if (isLive) return [];
    return (logs ?? []).slice(0, 8).map((l, i) => ({
      key: `${l.timestamp}-${i}`,
      timestamp: l.timestamp,
      level: l.level,
      severity: levelToSeverity(l.level),
      message: l.message,
    }));
  }, [isLive, logs]);

  const display = isLive ? liveLines : legacyLines;

  return (
    <div className={cn("w-full", className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Terminal className="h-4 w-4 text-[#00666d] dark:text-[#87edf6]" />
            <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
              Forensic Raw Logs
            </h3>
            {isLive && <LiveBadge state={conn.state} paused={paused} />}
          </div>
          <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] ml-6">
            {isLive
              ? "Last 5 events from /api/v1/logs/stream"
              : "Direct extraction from ELK-Sentinel stream"}
          </p>
        </div>
        {isLive && (
          <div className="flex items-center gap-2">
            <span
              className="text-[10px] tabular-nums text-[#497f8b] dark:text-[var(--strix-text-muted)]"
              title="Frames retained in the WS ring buffer (cap = 500)"
            >
              {retainedCount} frame{retainedCount === 1 ? "" : "s"} retained
            </span>
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              disabled={retainedCount === 0}
              className="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border border-[rgba(128,182,195,0.25)] dark:border-[var(--strix-border)] text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
              title={showAll ? "Collapse to last 5 events" : "Show every retained frame"}
            >
              {showAll ? "Collapse" : "View all"}
            </button>
            <button
              type="button"
              onClick={() => downloadForensicJson(live.frames.raw_log ?? [])}
              disabled={retainedCount === 0}
              className="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border border-[rgba(128,182,195,0.25)] dark:border-[var(--strix-border)] text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
              title="Download all retained raw_log frames as JSON"
            >
              JSON
            </button>
            <button
              type="button"
              onClick={() => downloadForensicCsv(live.frames.raw_log ?? [])}
              disabled={retainedCount === 0}
              className="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border border-[rgba(128,182,195,0.25)] dark:border-[var(--strix-border)] text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
              title="Download all retained raw_log frames as CSV"
            >
              CSV
            </button>
            <button
              onClick={() => setPaused((p) => !p)}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider transition-colors",
                paused
                  ? "bg-amber-500/15 text-amber-400 border border-amber-500/40 hover:bg-amber-500/25"
                  : "border border-[rgba(128,182,195,0.25)] dark:border-[var(--strix-border)] text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-gray-50 dark:hover:bg-gray-800",
              )}
              aria-pressed={paused}
              title={paused ? "Resume rendering — stream is still buffering" : "Pause rendering — stream keeps buffering"}
            >
              {paused ? <Play size={11} /> : <Pause size={11} />}
              {paused ? "Resume" : "Pause"}
            </button>
          </div>
        )}
      </div>

      {/* Log Terminal */}
      <div className="bg-[#0D1117] dark:bg-[#080C14] rounded-[24px] border border-[#1E293B] overflow-hidden">
        {/* Terminal header */}
        <div className="flex items-center gap-1.5 px-5 py-3 border-b border-[#1E293B]">
          <div className="h-3 w-3 rounded-full bg-red-500/70" />
          <div className="h-3 w-3 rounded-full bg-amber-500/70" />
          <div className="h-3 w-3 rounded-full bg-emerald-500/70" />
          <span className="text-[10px] text-gray-500 ml-3 font-mono">
            strix_sentinel_log_stream
          </span>
        </div>

        {/* Log lines */}
        <div
          className={cn(
            "p-5 font-mono text-[11px] leading-7 min-h-[180px] overflow-y-auto scrollbar-thin",
            showAll && "max-h-[640px]",
          )}
        >
          {display.length === 0 && (
            <div className="text-gray-500 italic px-3">
              {isLive ? "waiting for events…" : "no entries"}
            </div>
          )}
          {display.map((line) => {
            const sev = severityColors[line.severity];
            return (
              <div
                key={line.key}
                className="animate-slide-up-in flex gap-4 px-3 py-0.5 rounded-lg"
                style={{
                  backgroundColor: line.severity === "critical" || line.severity === "high" ? sev.bg : undefined,
                }}
              >
                <span className="text-gray-500 flex-shrink-0 select-none whitespace-nowrap">
                  {line.timestamp}
                </span>
                <span
                  className={cn(
                    "font-bold flex-shrink-0 min-w-[80px] uppercase",
                    FALLBACK_LEVEL_COLORS[line.level] ?? "",
                  )}
                  style={{
                    color: FALLBACK_LEVEL_COLORS[line.level] ? undefined : sev.fg,
                  }}
                >
                  {line.level}
                </span>
                <span className="text-gray-300 truncate">{line.message}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---- helpers ----------------------------------------------------------------

function LiveBadge({ state, paused }: { state: string; paused: boolean }) {
  const live = state === "open" && !paused;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider",
        live
          ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/40"
          : paused
            ? "bg-amber-500/15 text-amber-400 border border-amber-500/40"
            : "bg-gray-500/15 text-gray-400 border border-gray-500/40",
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          live ? "bg-emerald-400 animate-live-pulse" : paused ? "bg-amber-400" : "bg-gray-400",
        )}
      />
      {paused ? "PAUSED" : live ? "LIVE" : state.toUpperCase()}
    </span>
  );
}

// ---- export helpers ---------------------------------------------------------
// Forensic raw_log export — the artefact a SOC analyst or jury reviewer
// downloads as proof of every event the dashboard rendered. Pulls from the
// in-memory ring buffer (cap 500), preserves the FULL payload (alert id,
// rule id, MITRE tags, dqn action + score, full_log text), and stamps each
// row with the wallclock receive time so frames can be replayed in order.

interface RawLogFrame {
  type: string;
  ts: string;
  payload: RawLogPayload;
}

function projectExportRow(f: RawLogFrame): ForensicExportRow {
  const p = f.payload;
  const arr = (v: unknown): string =>
    Array.isArray(v) ? (v as string[]).filter((x) => typeof x === "string").join(";") : "";
  const num = (v: unknown): string =>
    typeof v === "number" ? Number(v).toFixed(6) : "";
  return {
    receivedAt: f.ts,
    occurredAt: (p.occurredAt as string) ?? "",
    alertId: (p.alertId as string) ?? (p.alert_id as string) ?? "",
    agentId: (p.agentId as string) ?? (p.agent_id as string) ?? "",
    chainId: (p.chainId as string) ?? "",
    ruleId: p.rule_id != null ? String(p.rule_id) : "",
    ckcStage: p.ckcStage != null ? String(p.ckcStage) : "",
    ckcStageName: (p.ckcStageName as string) ?? "",
    aeAnomalyScore: num(p.aeAnomalyScore),
    vaeMaliciousProb: num(p.vaeMaliciousProb),
    gnnNodeRisk: num(p.gnnNodeRisk),
    dqnAction: p.dqnAction != null ? String(p.dqnAction) : "",
    dqnActionName: (p.dqnActionName as string) ?? "",
    mitreTactics: arr(p.mitre_tactics),
    mitreTechniques: arr(p.mitreTechniques),
    description: (p.description as string) ?? "",
    fullLog: (p.full_log as string) ?? "",
  };
}

function downloadForensicJson(frames: ReadonlyArray<RawLogFrame>): void {
  const payload = {
    exportedAt: new Date().toISOString(),
    schema: "strix.raw-log.v1",
    count: frames.length,
    frames: frames.map((f) => ({
      receivedAt: f.ts,
      payload: f.payload,
    })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  triggerDownload(blob, `strix-forensic-logs-${stamp()}.json`);
}

function downloadForensicCsv(frames: ReadonlyArray<RawLogFrame>): void {
  const rows = frames.map(projectExportRow);
  const headers: Array<keyof ForensicExportRow> = [
    "receivedAt", "occurredAt", "alertId", "agentId", "chainId", "ruleId",
    "ckcStage", "ckcStageName",
    "aeAnomalyScore", "vaeMaliciousProb", "gnnNodeRisk",
    "dqnAction", "dqnActionName",
    "mitreTactics", "mitreTechniques",
    "description", "fullLog",
  ];
  const lines = [
    headers.join(","),
    ...rows.map((r) => headers.map((h) => csvCell(r[h])).join(",")),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  triggerDownload(blob, `strix-forensic-logs-${stamp()}.csv`);
}

function csvCell(v: string): string {
  if (/[,"\n]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
  return v;
}

function stamp(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function levelToSeverity(level: LogEntry["level"]): Severity {
  switch (level) {
    case "ERROR":
    case "BLOCK":
      return "critical";
    case "ALERT":
      return "high";
    case "WARN":
      return "medium";
    case "NOTICE":
    case "INFO":
    case "STRIX_AI":
      return "low";
    default:
      return "benign";
  }
}
