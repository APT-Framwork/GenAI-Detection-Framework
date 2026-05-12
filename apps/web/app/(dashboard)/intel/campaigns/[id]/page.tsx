// /intel/campaigns/[id] — campaign detail with its attributed chains.
"use client";

import Link from "next/link";
import { useAttributedChains, useCampaign } from "@/lib/api/intel";

export default function CampaignDetailPage({ params }: { params: { id: string } }) {
  const { id: campaignId } = params;
  const campaign = useCampaign(campaignId);
  const chains = useAttributedChains({ campaignId, limit: 50 });

  if (campaign.isLoading) {
    return (
      <div className="min-w-[1280px] flex items-center justify-center h-96 text-[#497f8b] text-sm">
        Loading campaign…
      </div>
    );
  }
  if (campaign.error || !campaign.data) {
    return (
      <div className="min-w-[1280px] flex items-center justify-center h-96 text-[#e88] text-sm">
        Campaign not found.
      </div>
    );
  }

  const c = campaign.data;

  return (
    <div className="min-w-[1280px] space-y-4">
      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-4">
        <p className="text-[10px] text-[#00666d] dark:text-strix-cyan uppercase tracking-[1.2px] font-bold mb-1">
          <Link href="/intel" className="hover:underline">Threat Intel</Link> ·{" "}
          <Link href="/intel/campaigns" className="hover:underline">Campaigns</Link>
        </p>
        <h1 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)] mb-2">
          {c.name}
        </h1>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] mb-3">
          {c.actorName && (
            <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              <span className="uppercase tracking-wider">Actor:</span>{" "}
              <Link href={`/intel/actors/${c.actorId}`} className="text-[#00666d] dark:text-strix-cyan hover:underline font-bold">
                {c.actorName}
              </Link>
              {c.actorMitreGroupId && <span className="ml-1 font-mono">({c.actorMitreGroupId})</span>}
            </span>
          )}
          <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            <span className="uppercase tracking-wider">Attribution targets:</span>{" "}
            <span className={`font-bold ${c.attributedChainCount > 0 ? "text-[#c44]" : "text-[#497f8b]"}`}>
              {c.attributedChainCount} chain{c.attributedChainCount === 1 ? "" : "s"}
            </span>
          </span>
        </div>
        <div className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-3">
          <span className="uppercase tracking-wider mr-2">Tactic chain:</span>
          <span className="font-mono text-[#00343d] dark:text-[var(--strix-text)]">{c.tacticChain.join(" → ")}</span>
        </div>
        {c.description && (
          <p className="text-[13px] text-[#00343d] dark:text-[var(--strix-text)] leading-relaxed border-t border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] pt-3 mt-2">
            {c.description}
          </p>
        )}
      </div>

      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-4">
        <h2 className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk)] mb-3">
          Attributed Chains
        </h2>
        {chains.data && chains.data.items.length > 0 ? (
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                <th className="text-left py-2 px-1">Host</th>
                <th className="text-left py-2 px-1">Opened</th>
                <th className="text-right py-2 px-1">CKC</th>
                <th className="text-right py-2 px-1">Confidence</th>
                <th className="text-left py-2 px-1">Triage</th>
                <th className="text-left py-2 px-1">Lifecycle</th>
              </tr>
            </thead>
            <tbody>
              {chains.data.items.map((r) => (
                <tr key={r.chainId} className="border-t border-[rgba(128,182,195,0.1)] dark:border-[var(--strix-border)]">
                  <td className="py-2 px-1 font-bold">{r.hostName ?? "—"}</td>
                  <td className="py-2 px-1 text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    {new Date(r.openedAt).toLocaleString()}
                  </td>
                  <td className="py-2 px-1 text-right font-mono">{r.maxCkcStage}</td>
                  <td className="py-2 px-1 text-right font-mono">{r.confidence}%</td>
                  <td className="py-2 px-1 text-[10px] uppercase tracking-wider">{r.triageStatus}</td>
                  <td className="py-2 px-1 text-[10px] uppercase tracking-wider">{r.lifecycleStatus}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] py-6 text-center italic">
            No chains attributed to this campaign yet.
          </div>
        )}
      </div>
    </div>
  );
}
