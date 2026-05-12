// /intel/actors — full actor list (drill-down from the landing page).
"use client";

import Link from "next/link";
import { useThreatActors } from "@/lib/api/intel";

export default function ActorsListPage() {
  const { data, isLoading } = useThreatActors(200);

  return (
    <div className="min-w-[1280px] space-y-4">
      <div className="flex items-center justify-between bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-3">
        <div>
          <p className="text-[10px] text-[#00666d] dark:text-strix-cyan uppercase tracking-[1.2px] font-bold mb-1">
            <Link href="/intel" className="hover:underline">Threat Intel</Link> · Actors
          </p>
          <h1 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            Tracked Threat Actors
          </h1>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {data?.total ?? 0} total
        </span>
      </div>

      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-4">
        {isLoading ? (
          <div className="py-8 text-center text-[#497f8b] dark:text-[var(--strix-text-muted)] text-sm">Loading…</div>
        ) : (
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                <th className="text-left py-2 px-1">Actor</th>
                <th className="text-left py-2 px-1">MITRE ID</th>
                <th className="text-left py-2 px-1">Country</th>
                <th className="text-left py-2 px-1">Motivation</th>
                <th className="text-left py-2 px-1">Aliases</th>
                <th className="text-right py-2 px-1">Campaigns</th>
                <th className="text-right py-2 px-1">Attributed</th>
                <th className="text-center py-2 px-1">Observed</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((a) => (
                <tr key={a.actorId} className="border-t border-[rgba(128,182,195,0.1)] dark:border-[var(--strix-border)] hover:bg-[rgba(128,182,195,0.05)]">
                  <td className="py-2 px-1">
                    <Link href={`/intel/actors/${a.actorId}`} className="font-bold text-[#00343d] dark:text-[var(--strix-text)] hover:text-[#00666d] dark:hover:text-strix-cyan">
                      {a.name}
                    </Link>
                  </td>
                  <td className="py-2 px-1 font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">{a.mitreGroupId ?? "—"}</td>
                  <td className="py-2 px-1 text-[#497f8b] dark:text-[var(--strix-text-muted)]">{a.country ?? "—"}</td>
                  <td className="py-2 px-1 text-[#497f8b] dark:text-[var(--strix-text-muted)]">{a.motivation ?? "—"}</td>
                  <td className="py-2 px-1 text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] max-w-[300px] truncate">{a.aliases.join(", ") || "—"}</td>
                  <td className="py-2 px-1 text-right font-mono">{a.campaignCount}</td>
                  <td className="py-2 px-1 text-right font-mono">{a.attributedChainCount}</td>
                  <td className="py-2 px-1 text-center">
                    {a.observedInEnv ? (
                      <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-[#c44]/10 text-[#c44] border border-[#c44]/30">Yes</span>
                    ) : (
                      <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#497f8b]/10 text-[#497f8b] border border-[#497f8b]/20">No</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
