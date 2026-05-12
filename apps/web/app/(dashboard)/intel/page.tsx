// -----------------------------------------------------------------------------
// /intel — CTI landing page. One-shot hydration from /intel/overview.
//
// Layout (top→bottom):
//   1. KPI strip — actors / campaigns / indicators / attributed chains
//   2. Threat-actor cards grid (one per actor)
//   3. Two-column split:
//        left  → Recent attributions table (chain → actor → campaign + confidence)
//        right → Top observed indicators (internal IOC extraction proof)
//   4. Campaign list footer with attribution counts
//
// All panels poll the overview endpoint every 15s. After a sim fires, the
// KPI counters tick up, attributions appear, and observed indicators
// accumulate hits — no manual refresh.
// -----------------------------------------------------------------------------

"use client";

import Link from "next/link";
import { useIntelOverview, type IntelFeed } from "@/lib/api/intel";
import { ObservableLink } from "@/components/intel/observable-drawer";

export default function IntelPage() {
  const { data, isLoading, error } = useIntelOverview();

  if (isLoading) {
    return (
      <div className="min-w-[1280px] flex items-center justify-center h-96 text-[#497f8b] dark:text-[var(--strix-text-muted)] text-sm uppercase tracking-wider">
        Loading CTI surface…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-w-[1280px] flex items-center justify-center h-96 text-[#e88] text-sm">
        Failed to load /intel/overview. Check API is reachable.
      </div>
    );
  }

  const { counts, topActors, topCampaigns, recentAttributions, topObservedIndicators, feeds } = data;

  return (
    <div className="min-w-[1280px] space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-3">
        <div>
          <p className="text-[10px] text-[#00666d] dark:text-strix-cyan uppercase tracking-[1.2px] font-bold mb-1">
            CYBER THREAT INTELLIGENCE
          </p>
          <h1 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            Threat Intel Surface
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/intel/actors"
            className="text-[10px] uppercase tracking-wider px-3 py-1.5 rounded-md border border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] text-[#00666d] dark:text-strix-cyan hover:bg-[rgba(128,182,195,0.08)]"
          >
            Actors →
          </Link>
          <Link
            href="/intel/campaigns"
            className="text-[10px] uppercase tracking-wider px-3 py-1.5 rounded-md border border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] text-[#00666d] dark:text-strix-cyan hover:bg-[rgba(128,182,195,0.08)]"
          >
            Campaigns →
          </Link>
          <Link
            href="/intel/graph"
            className="text-[10px] uppercase tracking-wider px-3 py-1.5 rounded-md border border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] text-[#00666d] dark:text-strix-cyan hover:bg-[rgba(128,182,195,0.08)]"
          >
            Graph →
          </Link>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-12 gap-4">
        <KpiTile label="Threat Actors" value={counts.actors} accent="cyan" />
        <KpiTile label="Campaigns" value={counts.campaigns} accent="cyan" />
        <KpiTile
          label="Indicators"
          value={counts.indicatorsTotal}
          sub={`${counts.indicatorsObservedInternal} observed internal`}
          accent="green"
        />
        <KpiTile
          label="Attributed Chains"
          value={counts.attributedChains}
          sub={`${counts.unattributedOpenChains} unattributed open`}
          accent="amber"
        />
      </div>

      {/* Subscribed feeds strip — proves "CAVIX ingests external intel". */}
      {feeds.length > 0 && (
        <Card title="Subscribed Feeds" subtitle="Live external CTI sources">
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            {feeds.map((f) => (
              <FeedTile key={f.feedId} feed={f} />
            ))}
          </div>
        </Card>
      )}

      {/* Actor cards */}
      <Card title="Tracked Threat Actors" subtitle="Public attribution per MITRE ATT&CK Groups">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {topActors.map((a) => (
            <Link
              key={a.actorId}
              href={`/intel/actors/${a.actorId}`}
              className="block group rounded-lg border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] hover:border-[rgba(128,182,195,0.5)] dark:hover:border-strix-cyan p-3 transition-colors bg-white dark:bg-[var(--strix-bg-deep)]"
            >
              <div className="flex items-start justify-between mb-1.5">
                <div className="font-bold text-[#00343d] dark:text-[var(--strix-text)] text-base font-[family-name:var(--font-space-grotesk)]">
                  {a.name}
                </div>
                {a.observedInEnv ? (
                  <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-[#a33]/10 text-[#c44] border border-[#c44]/30">
                    Observed
                  </span>
                ) : (
                  <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#497f8b]/10 text-[#497f8b] border border-[#497f8b]/20">
                    Catalog
                  </span>
                )}
              </div>
              <div className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider mb-2 flex items-center gap-2">
                {a.mitreGroupId && <span className="font-mono">{a.mitreGroupId}</span>}
                {a.country && <span>· {a.country}</span>}
              </div>
              {a.aliases.length > 0 && (
                <div className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-2 line-clamp-1">
                  aka: {a.aliases.slice(0, 3).join(", ")}
                </div>
              )}
              <div className="flex items-center gap-3 text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                <span>
                  <span className="text-[#00343d] dark:text-[var(--strix-text)] font-bold">{a.campaignCount}</span> campaigns
                </span>
                <span>
                  <span className="text-[#00343d] dark:text-[var(--strix-text)] font-bold">{a.attributedChainCount}</span> chains
                </span>
              </div>
            </Link>
          ))}
        </div>
      </Card>

      {/* Two-column row */}
      <div className="grid grid-cols-12 gap-4">
        {/* Recent attributions */}
        <div className="col-span-7">
          <Card title="Recent Attributions" subtitle="Auto-attribution via tactic-set Jaccard">
            {recentAttributions.length === 0 ? (
              <Empty>No attributed chains yet. Run `bash jury_demo.sh --apt APT29` to populate.</Empty>
            ) : (
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    <Th>Host</Th>
                    <Th>Actor</Th>
                    <Th>Campaign</Th>
                    <Th className="text-right">CKC</Th>
                    <Th className="text-right">Conf.</Th>
                    <Th>Opened</Th>
                  </tr>
                </thead>
                <tbody>
                  {recentAttributions.map((r) => (
                    <tr key={r.chainId} className="border-t border-[rgba(128,182,195,0.1)] dark:border-[var(--strix-border)]">
                      <Td>{r.hostName ?? "—"}</Td>
                      <Td>
                        {r.actorName ? (
                          <Link href={`/intel/actors/${r.actorId}`} className="text-[#00666d] dark:text-strix-cyan hover:underline">
                            {r.actorName}
                          </Link>
                        ) : "—"}
                      </Td>
                      <Td>
                        <Link href={`/intel/campaigns/${r.campaignId}`} className="text-[#00666d] dark:text-strix-cyan hover:underline">
                          {r.campaignName.slice(0, 40)}
                        </Link>
                      </Td>
                      <Td className="text-right font-mono">{r.maxCkcStage}</Td>
                      <Td className="text-right">
                        <ConfidencePill value={r.confidence} />
                      </Td>
                      <Td className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                        {fmtTime(r.openedAt)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>

        {/* Top observed IOCs */}
        <div className="col-span-5">
          <Card title="Top Observed Indicators" subtitle="CAVIX-internal extraction from alerts">
            {topObservedIndicators.length === 0 ? (
              <Empty>No internal observations yet. Run a sim to populate.</Empty>
            ) : (
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    <Th>Indicator</Th>
                    <Th>Type</Th>
                    <Th className="text-right">Hits</Th>
                    <Th className="text-right">TLP</Th>
                  </tr>
                </thead>
                <tbody>
                  {topObservedIndicators.map((i) => (
                    <tr key={i.indicatorId} className="border-t border-[rgba(128,182,195,0.1)] dark:border-[var(--strix-border)] hover:bg-[var(--strix-bg-surface)]">
                      <Td className="text-[11px] truncate max-w-[200px]">
                        <ObservableLink value={i.indicator} />
                      </Td>
                      <Td className="text-[10px] uppercase">{i.indicatorType}</Td>
                      <Td className="text-right font-mono">{i.internalHitCount}</Td>
                      <Td className="text-right">
                        <TlpBadge value={i.tlp} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      </div>

      {/* Campaign list */}
      <Card title="Campaigns" subtitle="Known adversary playbooks — Jaccard match targets">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              <Th>Campaign</Th>
              <Th>Actor</Th>
              <Th>Tactics</Th>
              <Th className="text-right">Chains Attributed</Th>
            </tr>
          </thead>
          <tbody>
            {topCampaigns.map((c) => (
              <tr key={c.campaignId} className="border-t border-[rgba(128,182,195,0.1)] dark:border-[var(--strix-border)]">
                <Td>
                  <Link href={`/intel/campaigns/${c.campaignId}`} className="text-[#00666d] dark:text-strix-cyan hover:underline">
                    {c.name}
                  </Link>
                </Td>
                <Td>{c.actorName ?? "—"}{c.actorMitreGroupId && <span className="text-[#497f8b] ml-1.5 text-[10px] font-mono">({c.actorMitreGroupId})</span>}</Td>
                <Td className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                  {c.tacticChain.join(" → ")}
                </Td>
                <Td className="text-right">
                  <span className={`font-bold ${c.attributedChainCount > 0 ? "text-[#c44]" : "text-[#497f8b]"}`}>
                    {c.attributedChainCount}
                  </span>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ---------- helpers ----------

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-4">
      <div className="mb-3">
        <h2 className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk)]">
          {title}
        </h2>
        {subtitle && (
          <p className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5">
            {subtitle}
          </p>
        )}
      </div>
      {children}
    </div>
  );
}

function KpiTile({ label, value, sub, accent }: { label: string; value: number; sub?: string; accent: "cyan" | "green" | "amber" }) {
  const colorMap = {
    cyan: "text-[#00666d] dark:text-strix-cyan",
    green: "text-[#2a8],dark:text-[#3c9]",
    amber: "text-[#d80],dark:text-[#fc4]",
  } as const;
  return (
    <div className="col-span-3 bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-4">
      <p className="text-[10px] uppercase tracking-[1.2px] font-bold text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-1">
        {label}
      </p>
      <div className={`text-[32px] font-bold leading-none font-[family-name:var(--font-space-grotesk)] ${colorMap[accent]}`}>
        {value.toLocaleString()}
      </div>
      {sub && (
        <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-1">
          {sub}
        </p>
      )}
    </div>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <th className={`text-left font-medium py-2 px-1 ${className}`}>{children}</th>;
}
function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`py-2 px-1 text-[#00343d] dark:text-[var(--strix-text)] ${className}`}>{children}</td>;
}

function ConfidencePill({ value }: { value: number }) {
  const color =
    value >= 70 ? "bg-[#c44]/10 text-[#c44] border-[#c44]/30"
    : value >= 50 ? "bg-[#d80]/10 text-[#d80] border-[#d80]/30"
    : "bg-[#497f8b]/10 text-[#497f8b] border-[#497f8b]/20";
  return (
    <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border ${color}`}>
      {value}%
    </span>
  );
}

function TlpBadge({ value }: { value: string }) {
  const color =
    value === "red" ? "bg-[#c44] text-white"
    : value === "amber" || value === "amber+strict" ? "bg-[#d80] text-white"
    : value === "green" ? "bg-[#2a8] text-white"
    : "bg-[#777] text-white";
  return (
    <span className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded ${color}`}>
      TLP:{value}
    </span>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)] py-6 text-center italic">
      {children}
    </div>
  );
}

function FeedTile({ feed }: { feed: IntelFeed }) {
  const ok = feed.lastStatus === "ok";
  const lastSeen = feed.lastPulledAt ? fmtTime(feed.lastPulledAt) : "never";
  const dot = !feed.enabled
    ? "bg-[#777]"
    : ok
    ? "bg-[#2a8]"
    : feed.lastStatus
    ? "bg-[#c44]"
    : "bg-[#d80]";
  const statusLabel = !feed.enabled
    ? "disabled"
    : ok
    ? "healthy"
    : feed.lastStatus
    ? feed.lastStatus.slice(0, 40)
    : "pending first pull";
  return (
    <div className="rounded-lg border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] p-3 bg-white dark:bg-[var(--strix-bg-deep)]">
      <div className="flex items-start justify-between mb-1.5">
        <div className="font-bold text-[13px] text-[#00343d] dark:text-[var(--strix-text)] truncate pr-2">
          {feed.name}
        </div>
        <span className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
          {statusLabel}
        </span>
      </div>
      <div className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider mb-2">
        {feed.kind} · every {Math.round(feed.pullIntervalS / 60)} min
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="Total" value={feed.indicatorCountTotal} />
        <Stat label="Last Pull" value={feed.lastIndicatorCount} />
        <Stat label="When" value={lastSeen} narrow />
      </div>
    </div>
  );
}

function Stat({ label, value, narrow }: { label: string; value: string | number; narrow?: boolean }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">{label}</div>
      <div className={`font-bold text-[#00343d] dark:text-[var(--strix-text)] ${narrow ? "text-[10px] truncate" : "text-[14px]"}`}>
        {value}
      </div>
    </div>
  );
}

function fmtTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}
