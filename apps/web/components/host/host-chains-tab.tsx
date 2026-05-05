"use client";

import Link from "next/link";
import type { HostChainEntry } from "@/lib/api/hosts";
import { severityFromCkcStage, severityColors } from "@/lib/design-tokens";

function dayTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.toLocaleDateString(undefined, { month: "short", day: "2-digit" })} ${d.toLocaleTimeString()}`;
  } catch {
    return iso;
  }
}

const TRIAGE_TINT: Record<string, string> = {
  new: "text-[#b31b25]",
  investigating: "text-amber-600 dark:text-amber-400",
  contained: "text-[#00666d] dark:text-[#87edf6]",
  closed: "text-[#497f8b] dark:text-[var(--strix-text-muted)]",
};

export function HostChainsTab({ rows }: { rows: HostChainEntry[] }) {
  if (rows.length === 0) {
    return (
      <div className="px-5 py-12 text-center text-[12px] italic text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        No attack chains have ever touched this host.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] border-b border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
            <th className="text-left px-3 py-2 w-[120px] font-medium">Chain</th>
            <th className="text-left px-3 py-2 w-[160px] font-medium">Opened</th>
            <th className="text-left px-3 py-2 w-[160px] font-medium">Closed</th>
            <th className="text-left px-3 py-2 font-medium">Lifecycle</th>
            <th className="text-left px-3 py-2 font-medium">Triage</th>
            <th className="text-left px-3 py-2 w-[120px] font-medium">Max CKC</th>
            <th className="text-right px-3 py-2 w-[80px] font-medium">Steps</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const sev = severityFromCkcStage(c.maxCkcStage);
            const sevColor = severityColors[sev];
            return (
              <tr
                key={c.chainId}
                className="border-b border-[rgba(128,182,195,0.08)] dark:border-[var(--strix-border)]/40 hover:bg-[var(--strix-bg-surface)]/30"
              >
                <td className="px-3 py-1.5 align-top">
                  <Link
                    href={`/attack-analysis/${c.chainId}`}
                    className="font-mono text-[11px] text-[#00666d] dark:text-[#87edf6] hover:underline"
                  >
                    {c.chainId.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-3 py-1.5 align-top font-mono text-[10px] text-[#00343d] dark:text-[var(--strix-text)] tabular-nums">
                  {dayTime(c.openedAt)}
                </td>
                <td className="px-3 py-1.5 align-top font-mono text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] tabular-nums">
                  {c.closedAt ? dayTime(c.closedAt) : "—"}
                </td>
                <td className="px-3 py-1.5 align-top">
                  <span className="text-[10px] uppercase tracking-wider text-[#00343d] dark:text-[var(--strix-text)]">
                    {c.status}
                  </span>
                </td>
                <td className="px-3 py-1.5 align-top">
                  <span
                    className={`text-[10px] uppercase tracking-wider font-bold ${TRIAGE_TINT[c.triageStatus] ?? ""}`}
                  >
                    {c.triageStatus}
                  </span>
                </td>
                <td className="px-3 py-1.5 align-top">
                  <span
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold tabular-nums"
                    style={{
                      backgroundColor: sevColor.bg,
                      color: sevColor.fg,
                      border: `1px solid ${sevColor.border}`,
                    }}
                  >
                    {c.maxCkcStage} · {c.maxCkcStageName}
                  </span>
                </td>
                <td className="px-3 py-1.5 align-top text-right tabular-nums text-[#00343d] dark:text-[var(--strix-text)]">
                  {c.stepCount}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
