// /intel/actors/[id] — actor detail page.
//   Hero block: name, MITRE ID, country, aliases, motivation, description.
//   Sections: associated campaigns + attributed chains.
"use client";

import Link from "next/link";
import {
  useAttributedChains,
  useCampaigns,
  useThreatActor,
} from "@/lib/api/intel";

export default function ActorDetailPage({ params }: { params: { id: string } }) {
  const { id: actorId } = params;
  const actor = useThreatActor(actorId);
  // Campaign list filtered client-side; the catalogue is tiny.
  const campaigns = useCampaigns(200);
  const chains = useAttributedChains({ actorId, limit: 50 });

  if (actor.isLoading) {
    return (
      <div className="min-w-[1280px] flex items-center justify-center h-96 text-[#497f8b] text-sm">
        Loading actor…
      </div>
    );
  }
  if (actor.error || !actor.data) {
    return (
      <div className="min-w-[1280px] flex items-center justify-center h-96 text-[#e88] text-sm">
        Actor not found.
      </div>
    );
  }

  const a = actor.data;
  const actorCampaigns = (campaigns.data?.items ?? []).filter((c) => c.actorId === actorId);

  return (
    <div className="min-w-[1280px] space-y-4">
      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-4">
        <p className="text-[10px] text-[#00666d] dark:text-strix-cyan uppercase tracking-[1.2px] font-bold mb-1">
          <Link href="/intel" className="hover:underline">Threat Intel</Link> ·{" "}
          <Link href="/intel/actors" className="hover:underline">Actors</Link>
        </p>
        <div className="flex items-baseline gap-3 mb-2">
          <h1 className="text-[28px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            {a.name}
          </h1>
          {a.mitreGroupId && (
            <span className="text-[12px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              {a.mitreGroupId}
            </span>
          )}
          {a.observedInEnv && (
            <span className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded bg-[#c44]/10 text-[#c44] border border-[#c44]/30">
              Observed in env
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-3">
          {a.country && <span><span className="uppercase tracking-wider">Country:</span> <span className="text-[#00343d] dark:text-[var(--strix-text)]">{a.country}</span></span>}
          {a.motivation && <span><span className="uppercase tracking-wider">Motivation:</span> <span className="text-[#00343d] dark:text-[var(--strix-text)]">{a.motivation}</span></span>}
          {a.aliases.length > 0 && (
            <span><span className="uppercase tracking-wider">Aliases:</span> <span className="text-[#00343d] dark:text-[var(--strix-text)]">{a.aliases.join(", ")}</span></span>
          )}
        </div>
        {a.description && (
          <p className="text-[13px] text-[#00343d] dark:text-[var(--strix-text)] leading-relaxed border-t border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] pt-3 mt-2">
            {a.description}
          </p>
        )}
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Card title="Campaigns" subtitle={`${actorCampaigns.length} tracked`} cols={5}>
          {actorCampaigns.length === 0 ? (
            <Empty>No campaigns linked.</Empty>
          ) : (
            <div className="space-y-2">
              {actorCampaigns.map((c) => (
                <Link
                  key={c.campaignId}
                  href={`/intel/campaigns/${c.campaignId}`}
                  className="block rounded-lg border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] hover:border-[rgba(128,182,195,0.5)] dark:hover:border-strix-cyan p-3"
                >
                  <div className="font-bold text-[#00343d] dark:text-[var(--strix-text)] text-[13px] mb-1">{c.name}</div>
                  <div className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-2">{c.tacticChain.join(" → ")}</div>
                  <div className="text-[10px]">
                    <span className={`font-bold ${c.attributedChainCount > 0 ? "text-[#c44]" : "text-[#497f8b]"}`}>
                      {c.attributedChainCount} chains attributed
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Card>

        <Card title="Attributed Chains" subtitle="Observed in your environment" cols={7}>
          {chains.data && chains.data.items.length > 0 ? (
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                  <th className="text-left py-2 px-1">Host</th>
                  <th className="text-left py-2 px-1">Campaign</th>
                  <th className="text-right py-2 px-1">CKC</th>
                  <th className="text-right py-2 px-1">Conf.</th>
                  <th className="text-left py-2 px-1">Triage</th>
                </tr>
              </thead>
              <tbody>
                {chains.data.items.map((r) => (
                  <tr key={r.chainId} className="border-t border-[rgba(128,182,195,0.1)] dark:border-[var(--strix-border)]">
                    <td className="py-2 px-1 font-bold">{r.hostName ?? "—"}</td>
                    <td className="py-2 px-1 text-[#497f8b] dark:text-[var(--strix-text-muted)]">{r.campaignName.slice(0, 40)}</td>
                    <td className="py-2 px-1 text-right font-mono">{r.maxCkcStage}</td>
                    <td className="py-2 px-1 text-right font-mono">{r.confidence}%</td>
                    <td className="py-2 px-1 text-[10px] uppercase tracking-wider text-[#497f8b]">{r.triageStatus}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>No attributed chains yet.</Empty>
          )}
        </Card>
      </div>
    </div>
  );
}

function Card({ title, subtitle, children, cols }: { title: string; subtitle?: string; children: React.ReactNode; cols: number }) {
  return (
    <div className={`col-span-${cols} bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-4`}>
      <div className="mb-3">
        <h2 className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk)]">
          {title}
        </h2>
        {subtitle && <p className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] py-6 text-center italic">
      {children}
    </div>
  );
}
