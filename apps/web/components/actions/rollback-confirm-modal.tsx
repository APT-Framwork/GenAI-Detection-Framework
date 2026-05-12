"use client";

import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import type { ActionItem } from "@/lib/api/actions";

interface RollbackConfirmModalProps {
  action: ActionItem;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
  busy: boolean;
}

export function RollbackConfirmModal({
  action,
  onCancel,
  onConfirm,
  busy,
}: RollbackConfirmModalProps) {
  const [hostInput, setHostInput] = useState("");
  const [reason, setReason] = useState("");
  const expectedHost = action.hostName ?? action.hostId.slice(0, 8);
  const hostMatch = hostInput.trim() === expectedHost;
  const reasonOk = reason.trim().length >= 4;
  const ok = hostMatch && reasonOk;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/55 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="bg-white dark:bg-[var(--strix-bg-card)] border border-[#b31b25]/40 rounded-xl shadow-2xl w-[480px] max-w-[92vw]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-2 px-5 py-3 border-b border-[#b31b25]/20 bg-[#b31b25]/5">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-[#b31b25]" />
            <h2 className="text-[14px] font-bold text-[#b31b25]">
              Roll back this action
            </h2>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00343d] dark:hover:text-[var(--strix-text)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-3">
          <div className="bg-[var(--strix-bg-surface)]/40 border border-[var(--strix-border)] rounded-md p-3 text-[11px] space-y-1">
            <p className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              Action
            </p>
            <p className="font-mono text-[12px] text-[#00343d] dark:text-[var(--strix-text)]">
              {action.actionName} on {expectedHost}
            </p>
            <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] font-mono">
              applied by {action.appliedBy?.name ?? "(automated)"} ·{" "}
              {action.appliedAt}
            </p>
          </div>

          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2.5 text-[11px] text-amber-700 dark:text-amber-400 leading-relaxed">
            <strong className="font-semibold">Audit-only:</strong> rolling back
            records the action as reverted in the ledger. CAVIX will{" "}
            <strong>not</strong> automatically un-isolate, un-block, or otherwise
            reverse the side effect — you must do that in the Wazuh / firewall
            console manually.
          </div>

          <label className="block">
            <span className="block text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-1">
              Type the host name to confirm:{" "}
              <span className="font-mono text-[#00343d] dark:text-[var(--strix-text)]">
                {expectedHost}
              </span>
            </span>
            <input
              type="text"
              value={hostInput}
              onChange={(e) => setHostInput(e.target.value)}
              autoFocus
              spellCheck={false}
              className={
                "w-full px-3 py-1.5 rounded-md text-[12px] font-mono bg-[var(--strix-bg-surface)] border " +
                (hostMatch
                  ? "border-emerald-500/50 text-emerald-700 dark:text-emerald-400"
                  : "border-[var(--strix-border)] text-[#00343d] dark:text-[var(--strix-text)]")
              }
            />
          </label>

          <label className="block">
            <span className="block text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-1">
              Reason
            </span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              maxLength={400}
              placeholder="why this action is being reversed (≥ 4 chars)…"
              className="w-full px-3 py-1.5 rounded-md text-[12px] bg-[var(--strix-bg-surface)] border border-[var(--strix-border)] text-[#00343d] dark:text-[var(--strix-text)] resize-none"
            />
          </label>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-[var(--strix-border)] flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="text-[11px] uppercase tracking-wider px-3 py-1.5 rounded text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-surface)]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(reason.trim())}
            disabled={!ok || busy}
            className="text-[11px] font-bold uppercase tracking-wider px-3 py-1.5 rounded bg-[#b31b25] text-white hover:bg-[#9b1620] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? "Rolling back…" : "Confirm rollback"}
          </button>
        </div>
      </div>
    </div>
  );
}
