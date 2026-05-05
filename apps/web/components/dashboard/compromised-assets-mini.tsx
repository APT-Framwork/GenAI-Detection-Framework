"use client";

import Link from "next/link";
import { ShieldAlert, ChevronRight } from "lucide-react";
import { useCompromisedAssets } from "@/lib/api/threat-intel";

export function CompromisedAssetsMini() {
  const q = useCompromisedAssets(5);
  const items = q.data?.items ?? [];

  return (
    <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-3.5 w-3.5 text-[#b31b25]" />
          <h3 className="text-[10px] font-bold uppercase tracking-[1px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            Compromised Assets
          </h3>
        </div>
        <Link
          href="/threat-intel"
          className="text-[10px] uppercase tracking-wider text-[#00666d] dark:text-[#87edf6] hover:underline flex items-center gap-0.5"
        >
          All <ChevronRight className="h-3 w-3" />
        </Link>
      </div>

      {items.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] italic">
            No compromised assets in window.
          </p>
        </div>
      ) : (
        <div className="space-y-1.5">
          {items.slice(0, 5).map((a) => {
            const vae = a.maxVaeProb != null ? Math.round(a.maxVaeProb * 100) : null;
            const gnn = a.maxGnnRisk != null ? Math.round(a.maxGnnRisk * 100) : null;
            return (
              <div
                key={a.hostId}
                className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg hover:bg-[#d6f6ff]/40 dark:hover:bg-[var(--strix-bg-surface)]/40 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] font-semibold text-[#00343d] dark:text-[var(--strix-text)] truncate">
                    {a.agentName ?? a.hostId.slice(0, 8)}
                  </p>
                  <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] font-mono truncate">
                    {a.ipAddress ?? "—"}
                  </p>
                </div>
                <div className="flex items-center gap-2 text-[10px] tabular-nums">
                  {vae != null && (
                    <span className="text-amber-600 dark:text-amber-400">VAE {vae}%</span>
                  )}
                  {gnn != null && (
                    <span className="text-[#b31b25]">GNN {gnn}%</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
