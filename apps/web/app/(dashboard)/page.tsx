"use client";

import { AptAttackTimeline } from "@/components/charts/apt-attack-timeline";
import { RlKillChain } from "@/components/charts/rl-kill-chain";
import { PredetectionReceipt } from "@/components/charts/predetection-receipt";
import { LiveStatusCard } from "@/components/dashboard/live-status-card";
import { SystemIntegrityCard } from "@/components/dashboard/system-integrity-card";
import { KpiThroughputCard } from "@/components/dashboard/kpi-throughput-card";
import { KpiCompositeF1Card } from "@/components/dashboard/kpi-composite-f1-card";
import { CompromisedAssetsMini } from "@/components/dashboard/compromised-assets-mini";
import { ThreatResolutionHistoryCard } from "@/components/dashboard/threat-resolution-history-card";
import { useLatestSimulationRun } from "@/lib/api/simulation";

export default function DashboardPage() {
  const latest = useLatestSimulationRun();
  const t = latest.data?.topology;

  return (
    <div className="min-w-[1280px] space-y-4">
      {/* Header — sim run banner. Connection status sits in the global topbar. */}
      <div className="flex items-center justify-between bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl px-5 py-3">
        <div>
          <p className="text-[10px] text-[#00666d] dark:text-strix-cyan uppercase tracking-[1.2px] font-bold mb-1">
            LIVE SENTINEL
          </p>
          <h1 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            Attack Timeline
          </h1>
        </div>
        <div className="flex items-center gap-4 text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {t?.run_id ? (
            <>
              <Pill k="run" v={t.run_id} />
              <Pill k="apt" v={(t.apt_group ?? t.apt) as string | undefined} />
              <Pill k="attacker" v={t.attacker_ip} />
              <Pill k="started" v={fmtTime(t.started_at)} />
            </>
          ) : (
            <span>awaiting topology…</span>
          )}
        </div>
      </div>

      {/* KPI strip — 4 metric tiles (executive snapshot). */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-3"><LiveStatusCard /></div>
        <div className="col-span-3"><SystemIntegrityCard /></div>
        <div className="col-span-3"><KpiThroughputCard /></div>
        <div className="col-span-3"><KpiCompositeF1Card /></div>
      </div>

      {/* Row — APT Attack Timeline (live, paced) | RL Intervention
          Timeline (frozen verdicts). Side-by-side per the design. */}
      <div className="grid grid-cols-12 gap-4">
        <Card className="col-span-6">
          <AptAttackTimeline />
        </Card>
        <Card className="col-span-6">
          <RlKillChain />
        </Card>
      </div>

      {/* Inline-variant predetection receipt — full-width below the grid. */}
      <PredetectionReceipt variant="inline" />

      {/* Bottom row — Compromised Assets + 7-day Threat Resolution chart. */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-6"><CompromisedAssetsMini /></div>
        <div className="col-span-6"><ThreatResolutionHistoryCard /></div>
      </div>
    </div>
  );
}

function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={
        "bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-5 " +
        (className ?? "")
      }
    >
      {children}
    </div>
  );
}

function Pill({ k, v }: { k: string; v: string | undefined | null }) {
  if (!v) return null;
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[rgba(128,182,195,0.25)] dark:border-[var(--strix-border)]">
      <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)]">{k}</span>
      <span className="font-mono text-[10px] text-[#00343d] dark:text-[var(--strix-text)]">
        {v}
      </span>
    </span>
  );
}

function fmtTime(iso: string | undefined | null): string | undefined {
  if (!iso) return undefined;
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}
