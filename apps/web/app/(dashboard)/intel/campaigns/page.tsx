// /intel/campaigns — full campaign list with attribution counts.
"use client";

import Link from "next/link";
import { useCampaigns } from "@/lib/api/intel";

export default function CampaignsListPage() {
  const { data, isLoading } = useCampaigns(200);

  return (
    <div className="min-w-[1280px] space-y-4">
      <div className="flex items-center justify-between bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-3">
        <div>
          <p className="text-[10px] text-[#00666d] dark:text-strix-cyan uppercase tracking-[1.2px] font-bold mb-1">
            <Link href="/intel" className="hover:underline">Threat Intel</Link> · Campaigns
          </p>
          <h1 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            Tracked Campaigns
          </h1>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {data?.total ?? 0} total
        </span>
      </div>

      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-4">
        {isLoading ? (
          <div className="py-8 text-center text-[#497f8b] text-sm">Loading…</div>
        ) : (
          <div className="space-y-3">
            {data?.items.map((c) => (
              <Link
                key={c.campaignId}
                href={`/intel/campaigns/${c.campaignId}`}
                className="block rounded-lg border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] hover:border-[rgba(128,182,195,0.5)] dark:hover:border-strix-cyan p-4 transition-colors"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="font-bold text-[#00343d] dark:text-[var(--strix-text)] text-[14px]">{c.name}</div>
                  <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${c.attributedChainCount > 0 ? "bg-[#c44]/10 text-[#c44] border-[#c44]/30" : "bg-[#497f8b]/10 text-[#497f8b] border-[#497f8b]/20"}`}>
                    {c.attributedChainCount} chains
                  </span>
                </div>
                {c.actorName && (
                  <div className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-2 uppercase tracking-wider">
                    Actor: <span className="text-[#00343d] dark:text-[var(--strix-text)] font-bold normal-case tracking-normal">{c.actorName}</span>
                    {c.actorMitreGroupId && <span className="ml-1 font-mono">({c.actorMitreGroupId})</span>}
                  </div>
                )}
                <div className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-2">
                  <span className="uppercase tracking-wider mr-2">Tactics:</span>
                  <span className="font-mono">{c.tacticChain.join(" → ")}</span>
                </div>
                {c.description && (
                  <p className="text-[11px] text-[#00343d] dark:text-[var(--strix-text)] leading-relaxed">
                    {c.description}
                  </p>
                )}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
