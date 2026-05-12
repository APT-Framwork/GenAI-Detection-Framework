// -----------------------------------------------------------------------------
// /actions — Response Action Log. Vertical timeline of DQN-proposed and
// operator-applied actions, with rollback (audit-only).
//
// Filter strip: status segmented control with live counts, time-range, host.
// Each row carries a q-value sparkline + status-derived action buttons.
// Rollback opens a confirm modal that requires typing the host name —
// destructive-action hygiene per the plan.
// -----------------------------------------------------------------------------

"use client";

import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import {
  type ActionItem,
  type ActionStatus,
  useActions,
  useApproveAction,
  useDeclineAction,
  useRollbackAction,
} from "@/lib/api/actions";
import { ActionRow } from "@/components/actions/action-row";
import { RollbackConfirmModal } from "@/components/actions/rollback-confirm-modal";
import { toast } from "@/lib/toast";

const STATUSES: ActionStatus[] = [
  "proposed",
  "approved",
  "auto_applied",
  "declined",
  "rolled_back",
];

const STATUS_LABEL: Record<ActionStatus, string> = {
  proposed: "Proposed",
  approved: "Approved",
  auto_applied: "Auto",
  declined: "Declined",
  rolled_back: "Rolled back",
};

const STATUS_DOT: Record<ActionStatus, string> = {
  proposed: "bg-amber-500",
  approved: "bg-[#00666d] dark:bg-[#87edf6]",
  auto_applied: "bg-emerald-500",
  declined: "bg-[rgba(128,182,195,0.6)]",
  rolled_back: "bg-[#b31b25]",
};

export default function ActionsPage() {
  const [activeStatus, setActiveStatus] = useState<ActionStatus[]>([]);
  const [hostQ, setHostQ] = useState("");
  const [rollbackTarget, setRollbackTarget] = useState<ActionItem | null>(null);

  const list = useActions({
    status: activeStatus.length > 0 ? activeStatus : undefined,
    limit: 100,
  });

  const approve = useApproveAction();
  const decline = useDeclineAction();
  const rollback = useRollbackAction();

  const items = useMemo(() => {
    const all = list.data?.items ?? [];
    if (!hostQ.trim()) return all;
    const q = hostQ.toLowerCase();
    return all.filter(
      (it) =>
        (it.hostName ?? "").toLowerCase().includes(q) ||
        it.hostId.toLowerCase().includes(q),
    );
  }, [list.data, hostQ]);

  const counts = list.data?.counts ?? {
    proposed: 0,
    approved: 0,
    auto_applied: 0,
    declined: 0,
    rolled_back: 0,
  };

  const toggleStatus = (s: ActionStatus) => {
    setActiveStatus((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
    );
  };

  const onApprove = async (it: ActionItem) => {
    try {
      await approve.mutateAsync({ actionId: it.actionId });
      toast.success(`Approved ${it.actionName} on ${it.hostName ?? it.hostId.slice(0, 8)}.`);
    } catch (e: unknown) {
      toast.warning(`Approve failed${e instanceof Error ? `: ${e.message}` : ""}`);
    }
  };

  const onDecline = async (it: ActionItem) => {
    const reason = window.prompt(
      `Reason for declining ${it.actionName} on ${it.hostName ?? it.hostId.slice(0, 8)}?`,
    );
    if (!reason || reason.trim().length < 1) return;
    try {
      await decline.mutateAsync({ actionId: it.actionId, reason: reason.trim() });
      toast.success("Declined.");
    } catch (e: unknown) {
      toast.warning(`Decline failed${e instanceof Error ? `: ${e.message}` : ""}`);
    }
  };

  const onRollback = (it: ActionItem) => setRollbackTarget(it);

  const confirmRollback = async (reason: string) => {
    if (!rollbackTarget) return;
    try {
      await rollback.mutateAsync({
        actionId: rollbackTarget.actionId,
        reason,
      });
      toast.success("Rollback recorded.");
      setRollbackTarget(null);
    } catch (e: unknown) {
      toast.warning(`Rollback failed${e instanceof Error ? `: ${e.message}` : ""}`);
    }
  };

  const busy = approve.isPending || decline.isPending || rollback.isPending;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-[1.2px] text-[#00666d] dark:text-strix-cyan font-bold">
            RESPONSE LEDGER
          </p>
          <h1 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            Action Log
          </h1>
        </div>
        <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] max-w-[480px]">
          Every STRIX-proposed action and every operator decision lands here.
          Rollback is <strong>audit-only</strong> — CAVIX records the reversal
          but does not undo the side effect at the host / firewall layer.
        </p>
      </div>

      {/* Filter strip */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="inline-flex items-center rounded-lg border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] overflow-hidden">
          <button
            type="button"
            onClick={() => setActiveStatus([])}
            className={
              "px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors " +
              (activeStatus.length === 0
                ? "bg-[var(--strix-bg-surface)] text-[#00343d] dark:text-[var(--strix-text)]"
                : "text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00343d] dark:hover:text-[var(--strix-text)]")
            }
          >
            All
          </button>
          {STATUSES.map((s) => {
            const on = activeStatus.includes(s);
            return (
              <button
                key={s}
                type="button"
                onClick={() => toggleStatus(s)}
                className={
                  "flex items-center gap-1.5 border-l border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors " +
                  (on
                    ? "bg-[var(--strix-bg-surface)] text-[#00343d] dark:text-[var(--strix-text)]"
                    : "text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00343d] dark:hover:text-[var(--strix-text)]")
                }
              >
                <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[s]}`} />
                <span>{STATUS_LABEL[s]}</span>
                <span className="tabular-nums opacity-70">{counts[s]}</span>
              </button>
            );
          })}
        </div>

        <input
          type="search"
          value={hostQ}
          onChange={(e) => setHostQ(e.target.value)}
          placeholder="filter by host…"
          className="flex-1 min-w-[200px] max-w-[340px] px-3 py-1.5 rounded border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] bg-transparent text-[12px] text-[#00343d] dark:text-[var(--strix-text)] placeholder:text-[#497f8b]/60"
        />

        <span className="ml-auto text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] tabular-nums">
          {items.length} visible
          {list.isFetching && (
            <Loader2 className="inline-block ml-2 h-3 w-3 animate-spin" />
          )}
        </span>
      </div>

      {/* Timeline */}
      <div className="relative bg-white dark:bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-lg overflow-hidden">
        {/* Vertical gutter rail */}
        <span
          className="absolute left-[15px] top-0 bottom-0 w-px bg-[rgba(128,182,195,0.25)] dark:bg-[var(--strix-border)]"
          aria-hidden
        />
        {list.isLoading && items.length === 0 ? (
          <EmptyState>Loading action log…</EmptyState>
        ) : items.length === 0 ? (
          <EmptyState>
            No actions in window. STRIX intervenes only when CKC ≥ ESCALATE
            — adjust the time range or status filter to find older entries.
          </EmptyState>
        ) : (
          items.map((it) => (
            <ActionRow
              key={it.actionId}
              item={it}
              onApprove={() => void onApprove(it)}
              onDecline={() => void onDecline(it)}
              onRollback={() => onRollback(it)}
              busy={busy}
            />
          ))
        )}
      </div>

      {rollbackTarget && (
        <RollbackConfirmModal
          action={rollbackTarget}
          onCancel={() => setRollbackTarget(null)}
          onConfirm={confirmRollback}
          busy={rollback.isPending}
        />
      )}
    </div>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-5 py-12 text-center text-[12px] italic text-[#497f8b] dark:text-[var(--strix-text-muted)]">
      {children}
    </div>
  );
}
