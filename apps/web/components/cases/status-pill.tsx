"use client";

import { type TriageStatus } from "@/lib/api/cases";

const STYLES: Record<TriageStatus, { rail: string; chip: string; text: string; label: string }> = {
  new: {
    rail: "bg-[#b31b25]",
    chip: "bg-[#b31b25]/12 border-[#b31b25]/40",
    text: "text-[#b31b25]",
    label: "NEW",
  },
  investigating: {
    rail: "bg-amber-500",
    chip: "bg-amber-500/12 border-amber-500/40",
    text: "text-amber-600 dark:text-amber-400",
    label: "INVESTIGATING",
  },
  contained: {
    rail: "bg-[#00666d] dark:bg-[#87edf6]",
    chip: "bg-[#00666d]/12 dark:bg-[#87edf6]/15 border-[#00666d]/40 dark:border-[#87edf6]/40",
    text: "text-[#00666d] dark:text-[#87edf6]",
    label: "CONTAINED",
  },
  closed: {
    rail: "bg-[rgba(128,182,195,0.4)]",
    chip: "bg-[rgba(128,182,195,0.12)] border-[rgba(128,182,195,0.35)]",
    text: "text-[#497f8b] dark:text-[var(--strix-text-muted)]",
    label: "CLOSED",
  },
};

export function StatusPill({ status }: { status: TriageStatus }) {
  const s = STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${s.chip} ${s.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.rail}`} />
      {s.label}
    </span>
  );
}

export function statusRail(status: TriageStatus): string {
  return STYLES[status].rail;
}
