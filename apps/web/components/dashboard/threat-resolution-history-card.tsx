"use client";

import { useMemo } from "react";
import { TrendingUp } from "lucide-react";
import { useNotifications } from "@/lib/api/analysis";

const DAY_MS = 86_400_000;

export function ThreatResolutionHistoryCard() {
  const notifications = useNotifications(500);

  const bars = useMemo(() => {
    const items = notifications.data?.items ?? [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const startMs = today.getTime() - 6 * DAY_MS;

    const buckets = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(startMs + i * DAY_MS);
      return {
        day: d.toLocaleDateString(undefined, { weekday: "short" }).slice(0, 3),
        count: 0,
      };
    });

    for (const it of items) {
      const t = Date.parse(it.decidedAt);
      if (!Number.isFinite(t)) continue;
      const idx = Math.floor((t - startMs) / DAY_MS);
      if (idx >= 0 && idx < 7) buckets[idx].count++;
    }
    const max = Math.max(1, ...buckets.map((b) => b.count));
    return buckets.map((b) => ({ ...b, height: (b.count / max) * 100 }));
  }, [notifications.data]);

  const total = bars.reduce((s, b) => s + b.count, 0);

  return (
    <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-3.5 w-3.5 text-[#00666d] dark:text-[#87edf6]" />
          <h3 className="text-[10px] font-bold uppercase tracking-[1px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            Threat Resolution · 7d
          </h3>
        </div>
        <span className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] tabular-nums">
          {total} interventions
        </span>
      </div>

      <div className="relative flex-1 min-h-[80px]">
        {total === 0 ? (
          <div
            className="absolute inset-0 flex items-center justify-center text-[10px] italic text-[#497f8b] dark:text-[var(--strix-text-muted)] rounded-md"
            style={{
              backgroundImage:
                "repeating-linear-gradient(45deg, transparent, transparent 6px, rgba(135,237,246,0.06) 6px, rgba(135,237,246,0.06) 7px)",
              border: "1px dashed rgba(135,237,246,0.25)",
            }}
          >
            awaiting STRIX interventions…
          </div>
        ) : (
          <div className="flex h-full items-end justify-between gap-1.5">
            {bars.map((b, i) => (
              <div key={i} className="flex flex-col items-center justify-end gap-1.5 flex-1 h-full">
                <span className="text-[9px] tabular-nums text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                  {b.count > 0 ? b.count : ""}
                </span>
                <div
                  className="w-full bg-[#00666d] dark:bg-[#87edf6] rounded-t-md transition-all"
                  style={{
                    height: `${Math.max(b.count > 0 ? 8 : 2, b.height)}%`,
                    opacity: b.count > 0 ? 0.9 : 0.18,
                  }}
                  title={`${b.day} · ${b.count}`}
                />
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="flex justify-between mt-2">
        {bars.map((b, i) => (
          <span
            key={i}
            className="text-[9px] uppercase font-bold text-[#497f8b] dark:text-[var(--strix-text-muted)] flex-1 text-center"
          >
            {b.day}
          </span>
        ))}
      </div>
    </div>
  );
}
