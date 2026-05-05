"use client";

import { Shield } from "lucide-react";
import { useTopology } from "@/lib/api/topology";
import { useLiveFeed } from "@/lib/api/live-feed";

export function SystemIntegrityCard() {
  const topology = useTopology("24h");
  const liveFeed = useLiveFeed({ maxEvents: 1 });

  const nodes = topology.data?.nodes ?? [];
  const total = nodes.length;
  const compromised = nodes.filter((n) => n.status === "compromised").length;
  const healthPct = total === 0 ? 100 : Math.max(0, 100 - (compromised / total) * 100);
  const sentinelOnline = liveFeed.status === "open";

  return (
    <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-4 flex flex-col">
      <div className="flex items-center gap-2 mb-2">
        <Shield className="h-3.5 w-3.5 text-[#00666d] dark:text-[#87edf6]" />
        <h3 className="text-[10px] font-bold uppercase tracking-[1px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          System Integrity
        </h3>
      </div>

      <div className="flex items-end justify-between mb-1">
        <span className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] leading-none tabular-nums">
          {healthPct.toFixed(1)}%
        </span>
        <span className={`text-[10px] font-bold uppercase tracking-wider ${sentinelOnline ? "text-emerald-500" : "text-amber-500"}`}>
          {sentinelOnline ? "● ACTIVE" : "○ IDLE"}
        </span>
      </div>
      <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-2">
        {compromised} compromised · {total} hosts
      </p>

      <div className="h-1.5 rounded-full bg-[rgba(128,182,195,0.15)] dark:bg-[var(--strix-border)] overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${compromised > 0 ? "bg-[#b31b25]" : "bg-emerald-500"}`}
          style={{ width: `${100 - healthPct}%` }}
        />
      </div>
    </div>
  );
}
