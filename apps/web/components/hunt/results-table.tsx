"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, ChevronDown } from "lucide-react";
import type { HuntResultItem } from "@/lib/api/hunt";
import { severityFromCkcStage, severityColors } from "@/lib/design-tokens";

function timeOf(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.toLocaleDateString(undefined, { month: "short", day: "2-digit" })} ${d.toLocaleTimeString()}`;
  } catch {
    return iso;
  }
}

interface ResultsTableProps {
  rows: HuntResultItem[];
  total: number;
  loading: boolean;
  loadMore?: () => void;
  hasMore: boolean;
}

export function ResultsTable({
  rows,
  total,
  loading,
  loadMore,
  hasMore,
}: ResultsTableProps) {
  if (rows.length === 0 && !loading) {
    return (
      <div className="border border-[var(--strix-border)] rounded-lg p-12 text-center text-[12px] italic text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        No alerts match this query in the current window.
      </div>
    );
  }

  return (
    <div className="border border-[var(--strix-border)] rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-[var(--strix-border)] bg-[var(--strix-bg-surface)]/40 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          Results <span className="tabular-nums ml-1">{rows.length}</span>
          {total > rows.length && (
            <span className="ml-1 opacity-70">of ~{total.toLocaleString()}</span>
          )}
        </span>
        {hasMore && loadMore && (
          <button
            type="button"
            onClick={loadMore}
            disabled={loading}
            className="text-[10px] uppercase tracking-wider px-2 py-1 rounded border border-[var(--strix-border)] text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-card)] disabled:opacity-50"
          >
            Load more
          </button>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] border-b border-[var(--strix-border)]">
              <th className="text-left px-3 py-1.5 w-[24px]" />
              <th className="text-left px-3 py-1.5 w-[140px] font-medium">Time</th>
              <th className="text-left px-3 py-1.5 w-[140px] font-medium">Host</th>
              <th className="text-left px-3 py-1.5 w-[80px] font-medium">Rule</th>
              <th className="text-left px-3 py-1.5 w-[80px] font-medium">CKC</th>
              <th className="text-left px-3 py-1.5 font-medium">Description</th>
              <th className="text-left px-3 py-1.5 w-[160px] font-medium">MITRE</th>
              <th className="text-left px-3 py-1.5 w-[100px] font-medium">Chain</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Row key={r.alertId} r={r} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({ r }: { r: HuntResultItem }) {
  const [open, setOpen] = useState(false);
  const sev = severityFromCkcStage(r.ckcStage ?? 0);
  const sevColor = severityColors[sev];
  return (
    <>
      <tr className="border-b border-[var(--strix-border)]/40 hover:bg-[var(--strix-bg-surface)]/30">
        <td className="px-3 py-1.5">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00343d] dark:hover:text-[var(--strix-text)]"
          >
            {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        </td>
        <td className="px-3 py-1.5 font-mono tabular-nums text-[#00343d] dark:text-[var(--strix-text)] whitespace-nowrap">
          {timeOf(r.ts)}
        </td>
        <td className="px-3 py-1.5">
          {r.hostId ? (
            <Link
              href={`/host/${r.hostId}`}
              className="text-[#00666d] dark:text-[#87edf6] hover:underline"
            >
              {r.hostName ?? r.hostId.slice(0, 8)}
            </Link>
          ) : (
            <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)]">—</span>
          )}
        </td>
        <td className="px-3 py-1.5 font-mono text-[10px] text-[#00343d] dark:text-[var(--strix-text)]">
          {r.ruleId ?? "—"}
        </td>
        <td className="px-3 py-1.5">
          <span
            className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold tabular-nums"
            style={{
              backgroundColor: sevColor.bg,
              color: sevColor.fg,
              border: `1px solid ${sevColor.border}`,
            }}
            title={r.ckcStageName ?? ""}
          >
            {r.ckcStage ?? 0}
          </span>
        </td>
        <td className="px-3 py-1.5 text-[#00343d] dark:text-[var(--strix-text)] max-w-[420px]">
          <span className="font-mono text-[10px] line-clamp-1 leading-snug">
            {r.description ?? "—"}
          </span>
        </td>
        <td className="px-3 py-1.5">
          <div className="flex flex-wrap gap-1">
            {(r.mitreTechniques ?? []).slice(0, 3).map((t) => (
              <span
                key={t}
                className="text-[9px] font-mono px-1 py-0.5 rounded bg-purple-500/10 text-purple-600 dark:text-purple-400"
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
        <td className="px-3 py-1.5">
          {r.chainId ? (
            <Link
              href={`/attack-analysis/${r.chainId}`}
              className="font-mono text-[10px] text-[#00666d] dark:text-[#87edf6] hover:underline"
            >
              {r.chainId.slice(0, 8)}
            </Link>
          ) : (
            <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)]">—</span>
          )}
        </td>
      </tr>
      {open && (
        <tr className="border-b border-[var(--strix-border)]/40 bg-[var(--strix-bg-surface)]/20">
          <td colSpan={8} className="px-6 py-3">
            <div className="space-y-1.5 text-[11px]">
              <div className="flex gap-4 text-[#497f8b] dark:text-[var(--strix-text-muted)] font-mono text-[9px] uppercase">
                <span>alert {r.alertId}</span>
                {r.ckcStageName && <span>· {r.ckcStageName}</span>}
              </div>
              <pre className="font-mono text-[10px] text-[#00343d] dark:text-[var(--strix-text)] whitespace-pre-wrap leading-relaxed">
                {r.description ?? "(no full_log captured)"}
              </pre>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
