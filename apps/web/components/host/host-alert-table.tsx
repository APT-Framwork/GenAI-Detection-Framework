"use client";

import Link from "next/link";
import type { HostAlertEntry } from "@/lib/api/hosts";
import { severityFromCkcStage, severityColors } from "@/lib/design-tokens";

function timeOf(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function dayOf(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "2-digit",
    });
  } catch {
    return iso;
  }
}

interface HostAlertTableProps {
  rows: HostAlertEntry[];
  empty: string;
}

export function HostAlertTable({ rows, empty }: HostAlertTableProps) {
  if (rows.length === 0) {
    return (
      <div className="px-5 py-12 text-center text-[12px] italic text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        {empty}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] border-b border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)]">
            <th className="text-left px-3 py-2 w-[100px] font-medium">Time</th>
            <th className="text-left px-3 py-2 w-[120px] font-medium">Decoder</th>
            <th className="text-left px-3 py-2 w-[88px] font-medium">CKC</th>
            <th className="text-left px-3 py-2 font-medium">Detail</th>
            <th className="text-left px-3 py-2 w-[140px] font-medium">MITRE</th>
            <th className="text-left px-3 py-2 w-[100px] font-medium">Chain</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const sev = severityFromCkcStage(r.ckcStage ?? 0);
            const sevColor = severityColors[sev];
            return (
              <tr
                key={r.alertId}
                className="border-b border-[rgba(128,182,195,0.08)] dark:border-[var(--strix-border)]/40 hover:bg-[var(--strix-bg-surface)]/30 transition-colors"
              >
                <td className="px-3 py-1.5 align-top text-[#00343d] dark:text-[var(--strix-text)] tabular-nums whitespace-nowrap">
                  <span className="block text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    {dayOf(r.occurredAt)}
                  </span>
                  <span className="font-mono">{timeOf(r.occurredAt)}</span>
                </td>
                <td className="px-3 py-1.5 align-top">
                  <span className="font-mono text-[10px] text-[#00343d] dark:text-[var(--strix-text)]">
                    {r.decoderName ?? "—"}
                  </span>
                  {r.location && (
                    <span className="block text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] font-mono truncate max-w-[120px]">
                      {r.location}
                    </span>
                  )}
                </td>
                <td className="px-3 py-1.5 align-top">
                  <span
                    className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold tabular-nums"
                    style={{
                      backgroundColor: sevColor.bg,
                      color: sevColor.fg,
                      border: `1px solid ${sevColor.border}`,
                    }}
                  >
                    {r.ckcStage ?? 0}
                  </span>
                </td>
                <td className="px-3 py-1.5 align-top text-[#00343d] dark:text-[var(--strix-text)] max-w-[460px]">
                  {r.ruleId && (
                    <span className="block text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                      rule {r.ruleId}
                    </span>
                  )}
                  <span className="font-mono text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] line-clamp-2 leading-snug">
                    {r.fullLog ?? "—"}
                  </span>
                </td>
                <td className="px-3 py-1.5 align-top">
                  <div className="flex flex-wrap gap-1">
                    {(r.mitreTechniques ?? []).slice(0, 3).map((t) => (
                      <span
                        key={t}
                        className="text-[9px] font-mono px-1 py-0.5 rounded bg-[rgba(128,182,195,0.1)] dark:bg-[var(--strix-bg-surface)] text-[#497f8b] dark:text-[var(--strix-text-muted)]"
                      >
                        {t}
                      </span>
                    ))}
                    {(r.mitreTechniques ?? []).length > 3 && (
                      <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                        +{r.mitreTechniques.length - 3}
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-1.5 align-top">
                  {r.chainId ? (
                    <Link
                      href={`/attack-analysis/${r.chainId}`}
                      className="font-mono text-[10px] text-[#00666d] dark:text-[#87edf6] hover:underline"
                    >
                      {r.chainId.slice(0, 8)}
                    </Link>
                  ) : (
                    <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
