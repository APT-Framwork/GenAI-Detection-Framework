"use client";

import { BarChart3 } from "lucide-react";
import { compositeMetrics } from "@/lib/model-registry";

export function KpiCompositeF1Card() {
  const composite = compositeMetrics();

  return (
    <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <BarChart3 className="h-3.5 w-3.5 text-[#00666d] dark:text-[#87edf6]" />
        <h3 className="text-[10px] font-bold uppercase tracking-[1px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          Composite F1
        </h3>
      </div>
      <span className="text-[28px] font-bold text-[#00343d] dark:text-[var(--strix-text)] leading-none tabular-nums">
        {composite.f1.toFixed(3)}
      </span>
      <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-2">
        {composite.modelCount} models · harmonic mean
      </p>
    </div>
  );
}
