"use client";

import { Filter } from "lucide-react";
import type { CaseCounts, TriageStatus } from "@/lib/api/cases";

const STATUSES: TriageStatus[] = ["new", "investigating", "contained", "closed"];

const TILE: Record<TriageStatus, { label: string; rail: string }> = {
  new:           { label: "NEW",            rail: "bg-[#b31b25]" },
  investigating: { label: "INVESTIGATING",  rail: "bg-amber-500" },
  contained:     { label: "CONTAINED",      rail: "bg-[#00666d] dark:bg-[#87edf6]" },
  closed:        { label: "CLOSED",         rail: "bg-[rgba(128,182,195,0.4)]" },
};

interface FiltersBarProps {
  active: TriageStatus[];                  // empty array = all
  counts: CaseCounts;
  onToggle: (s: TriageStatus) => void;
  onClear: () => void;
  minCkc: number;
  onMinCkc: (n: number) => void;
  hostQuery: string;
  onHostQuery: (s: string) => void;
}

export function FiltersBar({
  active,
  counts,
  onToggle,
  onClear,
  minCkc,
  onMinCkc,
  hostQuery,
  onHostQuery,
}: FiltersBarProps) {
  const isAll = active.length === 0;

  return (
    <div className="sticky top-0 z-10 bg-white dark:bg-[var(--strix-bg)] border-b border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] px-4 py-3 flex items-center gap-3 flex-wrap">
      {/* Status segmented control with counters */}
      <div className="inline-flex items-center rounded-lg border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] overflow-hidden">
        <button
          type="button"
          onClick={onClear}
          className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors ${
            isAll
              ? "bg-[var(--strix-bg-surface)] text-[#00343d] dark:text-[var(--strix-text)]"
              : "text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00343d] dark:hover:text-[var(--strix-text)]"
          }`}
        >
          All
        </button>
        {STATUSES.map((s) => {
          const t = TILE[s];
          const on = active.includes(s);
          return (
            <button
              key={s}
              type="button"
              onClick={() => onToggle(s)}
              className={`flex items-center gap-1.5 border-l border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors ${
                on
                  ? "bg-[var(--strix-bg-surface)] text-[#00343d] dark:text-[var(--strix-text)]"
                  : "text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00343d] dark:hover:text-[var(--strix-text)]"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${t.rail}`} />
              <span>{t.label}</span>
              <span className="tabular-nums opacity-70">{counts[s]}</span>
            </button>
          );
        })}
      </div>

      {/* Min-CKC filter */}
      <label className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        CKC ≥
        <input
          type="number"
          min={0}
          max={7}
          value={minCkc}
          onChange={(e) => onMinCkc(Math.max(0, Math.min(7, Number(e.target.value) || 0)))}
          className="w-12 px-1.5 py-1 rounded border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] bg-transparent text-[12px] tabular-nums text-[#00343d] dark:text-[var(--strix-text)]"
        />
      </label>

      {/* Host search */}
      <input
        type="search"
        value={hostQuery}
        onChange={(e) => onHostQuery(e.target.value)}
        placeholder="filter by host…"
        className="flex-1 min-w-[200px] max-w-[340px] px-3 py-1.5 rounded border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] bg-transparent text-[12px] text-[#00343d] dark:text-[var(--strix-text)] placeholder:text-[#497f8b]/60"
      />

      <Filter className="h-3.5 w-3.5 text-[#497f8b] dark:text-[var(--strix-text-muted)] ml-auto" />
    </div>
  );
}
