"use client";

import Link from "next/link";
import {
  Hourglass,
  CheckCircle2,
  XCircle,
  Undo2,
  Zap,
} from "lucide-react";
import type { ActionItem, ActionStatus } from "@/lib/api/actions";
import { severityFromCkcStage, severityColors } from "@/lib/design-tokens";

const STATUS_TINT: Record<
  ActionStatus,
  { fg: string; bg: string; label: string; Icon: typeof Hourglass }
> = {
  proposed: {
    fg: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-500/10 border-amber-500/30",
    label: "PROPOSED",
    Icon: Hourglass,
  },
  approved: {
    fg: "text-[#00666d] dark:text-[#87edf6]",
    bg: "bg-[#00666d]/10 dark:bg-[#87edf6]/10 border-[#00666d]/30 dark:border-[#87edf6]/30",
    label: "APPROVED",
    Icon: CheckCircle2,
  },
  auto_applied: {
    fg: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-500/10 border-emerald-500/30",
    label: "AUTO-APPLIED",
    Icon: Zap,
  },
  declined: {
    fg: "text-[#497f8b] dark:text-[var(--strix-text-muted)]",
    bg: "bg-[rgba(128,182,195,0.08)] border-[rgba(128,182,195,0.3)]",
    label: "DECLINED",
    Icon: XCircle,
  },
  rolled_back: {
    fg: "text-[#b31b25]",
    bg: "bg-[#b31b25]/10 border-[#b31b25]/30",
    label: "ROLLED BACK",
    Icon: Undo2,
  },
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return `${d.toLocaleDateString(undefined, { month: "short", day: "2-digit" })} ${d.toLocaleTimeString()}`;
  } catch {
    return iso;
  }
}

interface ActionRowProps {
  item: ActionItem;
  onApprove: () => void;
  onDecline: () => void;
  onRollback: () => void;
  busy: boolean;
}

export function ActionRow({
  item,
  onApprove,
  onDecline,
  onRollback,
  busy,
}: ActionRowProps) {
  const tint = STATUS_TINT[item.status];
  const Icon = tint.Icon;
  const sev = severityFromCkcStage(item.ckcStageAtDecision);
  const sevColor = severityColors[sev];

  return (
    <div className="relative flex gap-4 pl-8 pr-4 py-3 border-b border-[rgba(128,182,195,0.1)] dark:border-[var(--strix-border)]/40 hover:bg-[var(--strix-bg-surface)]/30 transition-colors">
      {/* Vertical timeline gutter dot */}
      <span
        className={`absolute left-3 top-5 h-2.5 w-2.5 rounded-full ring-2 ring-white dark:ring-[var(--strix-bg)] ${
          item.status === "proposed"
            ? "bg-amber-500"
            : item.status === "approved" || item.status === "auto_applied"
            ? "bg-emerald-500"
            : item.status === "declined"
            ? "bg-[rgba(128,182,195,0.5)]"
            : "bg-[#b31b25]"
        }`}
        aria-hidden
      />

      {/* Time + status */}
      <div className="w-[140px] shrink-0">
        <p className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] tabular-nums">
          {fmtTime(item.decidedAt)}
        </p>
        <span
          className={`mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider border ${tint.bg} ${tint.fg}`}
        >
          <Icon className="h-3 w-3" />
          {tint.label}
        </span>
      </div>

      {/* Body */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[14px] font-bold font-mono text-[#00343d] dark:text-[var(--strix-text)] tracking-tight">
            {item.actionName}
          </span>
          <span className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">on</span>
          <Link
            href={`/host/${item.hostId}`}
            className="text-[12px] font-semibold text-[#00666d] dark:text-[#87edf6] hover:underline"
          >
            {item.hostName ?? item.hostId.slice(0, 8)}
          </Link>
          <span
            className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold tabular-nums"
            style={{
              backgroundColor: sevColor.bg,
              color: sevColor.fg,
              border: `1px solid ${sevColor.border}`,
            }}
            title={item.ckcStageName}
          >
            CKC {item.ckcStageAtDecision}
          </span>
          <Link
            href={`/attack-analysis/${item.chainId}`}
            className="font-mono text-[10px] text-[#00666d] dark:text-[#87edf6] hover:underline ml-auto"
          >
            chain {item.chainId.slice(0, 8)}
          </Link>
        </div>

        <div className="mt-1.5 flex items-center gap-3 flex-wrap text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          <QValueSparkline qValues={item.qValues} chosen={item.action} />
          {item.appliedBy && (
            <span>
              applied by <span className="font-mono text-[#00343d] dark:text-[var(--strix-text)]">{item.appliedBy.name}</span>
              {item.appliedAt && <> · {fmtTime(item.appliedAt)}</>}
            </span>
          )}
          {item.rejectedBy && (
            <span>
              declined by <span className="font-mono text-[#00343d] dark:text-[var(--strix-text)]">{item.rejectedBy.name}</span>
              {item.rejectedAt && <> · {fmtTime(item.rejectedAt)}</>}
            </span>
          )}
          {item.rollback && (
            <span className="text-[#b31b25]">
              rolled back by <span className="font-mono">{item.rollback.rolledBackBy?.name ?? "—"}</span> · {fmtTime(item.rollback.rolledBackAt)}
              {item.rollback.reason && <> · "{item.rollback.reason}"</>}
            </span>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-start gap-1.5 shrink-0">
        {item.status === "proposed" && (
          <>
            <button
              type="button"
              onClick={onApprove}
              disabled={busy}
              className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded bg-[#00666d] dark:bg-[#87edf6] text-[#cffbff] dark:text-[#00343d] hover:opacity-90 disabled:opacity-50"
            >
              Approve
            </button>
            <button
              type="button"
              onClick={onDecline}
              disabled={busy}
              className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded border border-[rgba(128,182,195,0.4)] dark:border-[var(--strix-border)] text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-surface)] disabled:opacity-50"
            >
              Decline
            </button>
          </>
        )}
        {(item.status === "approved" || item.status === "auto_applied") && (
          <button
            type="button"
            onClick={onRollback}
            disabled={busy}
            className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded border border-[#b31b25]/40 text-[#b31b25] hover:bg-[#b31b25]/10 disabled:opacity-50"
          >
            <span className="inline-flex items-center gap-1">
              <Undo2 className="h-3 w-3" />
              Rollback
            </span>
          </button>
        )}
      </div>
    </div>
  );
}

// Q-value sparkline — 5 thin bars, one per action, chosen one tinted teal.
function QValueSparkline({
  qValues,
  chosen,
}: {
  qValues: number[];
  chosen: number;
}) {
  if (qValues.length === 0) {
    return (
      <span className="font-mono text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        q-values —
      </span>
    );
  }
  const min = Math.min(...qValues);
  const max = Math.max(...qValues);
  const span = Math.max(1e-6, max - min);
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-[9px] uppercase tracking-wider opacity-70">q</span>
      <span className="inline-flex items-end gap-[2px] h-4">
        {qValues.map((v, i) => {
          const h = Math.max(2, Math.round(((v - min) / span) * 14)) + 2;
          const isChosen = i === chosen;
          return (
            <span
              key={i}
              title={`a${i}=${v.toFixed(3)}`}
              className={
                "w-[3px] rounded-sm " +
                (isChosen
                  ? "bg-[#00666d] dark:bg-[#87edf6]"
                  : "bg-[rgba(128,182,195,0.5)] dark:bg-[rgba(128,182,195,0.35)]")
              }
              style={{ height: `${h}px` }}
            />
          );
        })}
      </span>
    </span>
  );
}
