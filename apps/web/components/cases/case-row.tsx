"use client";

import Link from "next/link";
import type { CaseItem } from "@/lib/api/cases";
import { statusRail } from "./status-pill";
import { severityFromCkcStage, severityColors } from "@/lib/design-tokens";

function timeAgo(iso: string): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "—";
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86_400)}d`;
}

interface CaseRowProps {
  item: CaseItem;
  selected: boolean;
  onSelect: (chainId: string, on: boolean) => void;
  flash: boolean;
}

export function CaseRow({ item, selected, onSelect, flash }: CaseRowProps) {
  const sev = severityFromCkcStage(item.maxCkcStage);
  const sevColor = severityColors[sev];
  const techPreview = item.mitreTechniques.slice(0, 3);
  const moreTech = Math.max(0, item.mitreTechniques.length - techPreview.length);

  return (
    <div
      className={`group relative flex items-center gap-3 h-8 pr-3 border-b border-[rgba(128,182,195,0.1)] dark:border-[var(--strix-border)]/50 transition-colors ${
        selected
          ? "bg-strix-cyan/5"
          : "hover:bg-[var(--strix-bg-surface)]/40"
      } ${flash ? "before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-[#87edf6] before:animate-pulse" : ""}`}
    >
      {/* Status rail (left edge) */}
      <span
        className={`absolute left-0 top-0 bottom-0 w-[3px] ${statusRail(item.status)}`}
        aria-hidden
      />

      {/* Checkbox */}
      <input
        type="checkbox"
        checked={selected}
        onChange={(e) => onSelect(item.chainId, e.target.checked)}
        onClick={(e) => e.stopPropagation()}
        className="ml-3 h-3 w-3 accent-[#00666d] dark:accent-[#87edf6] cursor-pointer"
      />

      {/* Chain ID (mono, truncated) */}
      <Link
        href={`/attack-analysis/${item.chainId}`}
        className="flex items-center gap-3 flex-1 min-w-0"
      >
        <span className="font-mono text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] tabular-nums w-[88px] truncate">
          {item.chainId.slice(0, 8)}
        </span>

        {/* Host */}
        <span className="text-[12px] text-[#00343d] dark:text-[var(--strix-text)] font-medium w-[140px] truncate">
          {item.hostName ?? "—"}
        </span>
        <span className="text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] w-[110px] truncate hidden lg:block">
          {item.hostIp ?? "—"}
        </span>

        {/* CKC stage badge */}
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold tabular-nums uppercase"
          style={{
            backgroundColor: sevColor.bg,
            color: sevColor.fg,
            border: `1px solid ${sevColor.border}`,
          }}
        >
          CKC {item.maxCkcStage}
          <span className="opacity-70 hidden xl:inline">· {item.maxCkcStageName}</span>
        </span>

        {/* MITRE techniques (max 3) */}
        <div className="flex items-center gap-1 flex-1 min-w-0 overflow-hidden">
          {techPreview.map((t) => (
            <span
              key={t}
              className="text-[9px] font-mono px-1 py-0.5 rounded bg-[rgba(128,182,195,0.1)] dark:bg-[var(--strix-bg-surface)] text-[#497f8b] dark:text-[var(--strix-text-muted)] whitespace-nowrap"
            >
              {t}
            </span>
          ))}
          {moreTech > 0 && (
            <span className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              +{moreTech}
            </span>
          )}
        </div>

        {/* Last DQN action */}
        <span className="text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] w-[100px] truncate hidden lg:block">
          {item.lastDqnAction ?? "—"}
        </span>

        {/* Age */}
        <span className="text-[10px] tabular-nums text-[#497f8b] dark:text-[var(--strix-text-muted)] w-[40px] text-right">
          {timeAgo(item.openedAt)}
        </span>

        {/* Assignee */}
        <span className="w-[28px] flex justify-center" title={item.assignee?.name ?? "unassigned"}>
          {item.assignee ? (
            <span className="h-5 w-5 rounded-full bg-[#00666d] dark:bg-[#87edf6] text-[#cffbff] dark:text-[#00343d] flex items-center justify-center text-[8px] font-bold uppercase">
              {(item.assignee.name[0] ?? "?").toUpperCase()}
            </span>
          ) : (
            <span className="h-5 w-5 rounded-full border border-dashed border-[rgba(128,182,195,0.4)] dark:border-[var(--strix-border)]" />
          )}
        </span>
      </Link>
    </div>
  );
}
