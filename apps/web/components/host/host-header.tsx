"use client";

import Link from "next/link";
import {
  ChevronLeft,
  Server,
  ShieldCheck,
  AlertTriangle,
  Skull,
} from "lucide-react";
import type { HostOverview, HostSummary } from "@/lib/api/hosts";

const STATUS_TINT: Record<
  HostOverview["status"],
  { fg: string; bg: string; border: string; label: string; Icon: typeof ShieldCheck }
> = {
  healthy: {
    fg: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
    label: "HEALTHY",
    Icon: ShieldCheck,
  },
  warning: {
    fg: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    label: "WARNING",
    Icon: AlertTriangle,
  },
  compromised: {
    fg: "text-[#b31b25]",
    bg: "bg-[#b31b25]/10",
    border: "border-[#b31b25]/40",
    label: "COMPROMISED",
    Icon: Skull,
  },
};

interface HostHeaderProps {
  host: HostOverview;
  summary: HostSummary;
}

export function HostHeader({ host, summary }: HostHeaderProps) {
  const tint = STATUS_TINT[host.status];
  const Icon = tint.Icon;

  return (
    <div className="sticky top-0 z-10 bg-white/95 dark:bg-[var(--strix-bg)]/95 backdrop-blur border-b border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] px-5 py-3">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        {/* Left: identity */}
        <div className="flex items-start gap-3 min-w-0">
          <Link
            href="/topology"
            className="mt-1 flex items-center gap-1 text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00343d] dark:hover:text-[var(--strix-text)]"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            Topology
          </Link>
          <span className="h-8 w-px bg-[rgba(128,182,195,0.2)] dark:bg-[var(--strix-border)]" />
          <div className="min-w-0">
            <div className="flex items-baseline gap-2 flex-wrap">
              <Server className="h-5 w-5 text-[#00666d] dark:text-[#87edf6] self-center" />
              <h1 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
                {host.name}
              </h1>
              <span className="font-mono text-[12px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                {host.ip ?? "—"}
              </span>
              {host.isManager && (
                <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#00666d]/10 text-[#00666d] dark:bg-[#87edf6]/10 dark:text-[#87edf6] border border-[#00666d]/20 dark:border-[#87edf6]/20">
                  Manager
                </span>
              )}
              <span
                className={`inline-flex items-center gap-1 text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${tint.bg} ${tint.fg} ${tint.border}`}
              >
                <Icon className="h-3 w-3" />
                {tint.label}
              </span>
            </div>
            <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-1 font-mono">
              agent {host.agentId} · host {host.hostId.slice(0, 8)}
            </p>
          </div>
        </div>

        {/* Right: summary tiles */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <Tile label="Open chains" value={summary.openChains} accent={summary.openChains > 0 ? "amber" : "muted"} />
          <Tile label="Alerts 24h" value={summary.totalAlerts24h} accent="muted" />
          <Tile
            label="Max CKC 24h"
            value={`${summary.maxCkcStage24h}/7`}
            sub={summary.maxCkcStageName24h}
            accent={summary.maxCkcStage24h >= 4 ? "red" : summary.maxCkcStage24h >= 1 ? "amber" : "muted"}
          />
          <Tile
            label="Last STRIX"
            value={summary.lastDqnAction ?? "—"}
            accent="muted"
          />
        </div>
      </div>
    </div>
  );
}

function Tile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: number | string;
  sub?: string;
  accent: "muted" | "amber" | "red";
}) {
  const accentText =
    accent === "red"
      ? "text-[#b31b25]"
      : accent === "amber"
      ? "text-amber-600 dark:text-amber-400"
      : "text-[#00343d] dark:text-[var(--strix-text)]";

  return (
    <div className="px-3 py-1.5 rounded-lg border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] min-w-[88px]">
      <p className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        {label}
      </p>
      <p className={`text-[14px] font-bold tabular-nums leading-tight ${accentText}`}>
        {value}
      </p>
      {sub && (
        <p className="text-[9px] uppercase text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5">
          {sub}
        </p>
      )}
    </div>
  );
}
