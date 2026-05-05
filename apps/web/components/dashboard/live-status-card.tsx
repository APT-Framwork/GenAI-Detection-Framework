"use client";

import { useMemo } from "react";
import { useLiveFeed } from "@/lib/api/live-feed";

function severityFromCkc(stage: number): "critical" | "high" | "medium" | "low" | "info" {
  if (stage >= 6) return "critical";
  if (stage >= 4) return "high";
  if (stage >= 2) return "medium";
  if (stage >= 1) return "low";
  return "info";
}

export function LiveStatusCard() {
  const liveFeed = useLiveFeed({ maxEvents: 200 });

  const counts = useMemo(() => {
    let crit = 0, warn = 0, upd = 0;
    for (const e of liveFeed.events) {
      const sev = severityFromCkc(e.data.ckcStage);
      if (sev === "critical") crit++;
      else if (sev === "high" || sev === "medium") warn++;
      else upd++;
    }
    return { crit, warn, upd };
  }, [liveFeed.events]);

  return (
    <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-4">
      <h3 className="text-[10px] font-bold uppercase tracking-[1px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-3">
        Live Status
      </h3>
      <div className="space-y-2.5">
        <Row color="bg-[#b31b25]" label="Critical" value={counts.crit} textOnDark />
        <Row color="bg-amber-500" label="Warnings" value={counts.warn} textOnDark />
        <Row color="bg-[#00666d]" label="Updates" value={counts.upd} textOnDark />
      </div>
    </div>
  );
}

function Row({ color, label, value, textOnDark }: { color: string; label: string; value: number; textOnDark: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2.5">
        <div className={`h-1.5 w-7 rounded-full ${color}`} />
        <span className="text-[12px] text-[#00343d] dark:text-[var(--strix-text)]">{label}</span>
      </div>
      <span className={`rounded-full ${color} px-2.5 py-0.5 text-[11px] font-bold ${textOnDark ? "text-white" : "text-[#00343d]"}`}>
        {String(value).padStart(2, "0")}
      </span>
    </div>
  );
}
