"use client";

import { useMemo } from "react";
import { Zap } from "lucide-react";
import { useLiveFeed } from "@/lib/api/live-feed";

export function KpiThroughputCard() {
  const liveFeed = useLiveFeed({ maxEvents: 500 });

  const perMin = useMemo(() => {
    const cutoff = Date.now() - 60_000;
    return liveFeed.events.filter((e) => {
      const t = Date.parse(e.data.occurredAt);
      return Number.isFinite(t) && t >= cutoff;
    }).length;
  }, [liveFeed.events]);

  return (
    <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <Zap className="h-3.5 w-3.5 text-[#00666d] dark:text-[#87edf6]" />
        <h3 className="text-[10px] font-bold uppercase tracking-[1px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          Throughput
        </h3>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-[28px] font-bold text-[#00343d] dark:text-[var(--strix-text)] leading-none tabular-nums">
          {perMin}
        </span>
        <span className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          /min
        </span>
      </div>
      <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-1">
        SSE feed {liveFeed.status}
      </p>
    </div>
  );
}
