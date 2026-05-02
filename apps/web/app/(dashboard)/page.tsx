// -----------------------------------------------------------------------------
// Dashboard page — Phase 9 final layout.
//
// Rows (min-width 1280):
//   * Header: simulation run header (run_id, attacker_ip, started_at).
//     The connection status pill lives in apps/web/components/layout/topbar.tsx.
//   * Two-column grid:
//       left  → SimulationTopologyPanel + RlKillChain
//       right → GraphEvolution (live) + DetectionQualityPanel
//   * Full-width: ForensicLogViewer (live tail).
//
// All ring buffers are bounded (ws.ts default cap 500; per-panel internal caps
// in their respective files). useEffect cleanups, intervals are cleared on
// unmount. No new wall-clock timers added at this layer.
// -----------------------------------------------------------------------------

"use client";

import { SimulationTopologyPanel } from "@/components/topology/simulation-topology-panel";
import { GraphEvolution } from "@/components/charts/graph-evolution";
import { ForensicLogViewer } from "@/components/charts/forensic-log-viewer";
import { AptAttackTimeline } from "@/components/charts/apt-attack-timeline";
import { RlKillChain } from "@/components/charts/rl-kill-chain";
import { DetectionQualityPanel } from "@/components/charts/detection-quality-panel";
import { PredetectionReceipt } from "@/components/charts/predetection-receipt";
import { useLatestSimulationRun } from "@/lib/api/simulation";

export default function DashboardPage() {
  const latest = useLatestSimulationRun();
  const t = latest.data?.topology;

  return (
    // Outer flex so the rail-variant of the predetection receipt can sit
    // sticky to the right of the main column. The main column keeps the
    // existing 1280-min-width grid; the rail is fixed-width 300px.
    <div className="min-w-[1280px] flex gap-4">
      <div className="flex-1 space-y-4">
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

        {/* Row 1 — Topology + Graph evolution */}
        <div className="grid grid-cols-12 gap-4">
          <Card className="col-span-6">
            <SimulationTopologyPanel />
          </Card>
          <Card className="col-span-6">
            <GraphEvolution />
          </Card>
        </div>

        {/* Row 2 — APT Attack Timeline (live, paced) | RL Intervention
            Timeline (frozen verdicts). Side-by-side per the design. */}
        <div className="grid grid-cols-12 gap-4">
          <Card className="col-span-6">
            <AptAttackTimeline />
          </Card>
          <Card className="col-span-6">
            <RlKillChain />
          </Card>
        </div>

        {/* Row 3 — Detection quality (full-width since it pairs naturally
            with the intervention timeline above and benefits from horizontal
            space for the AE | VAE side-by-side cards). */}
        <div className="grid grid-cols-12 gap-4">
          <Card className="col-span-12">
            <DetectionQualityPanel />
          </Card>
        </div>

        {/* Inline-variant predetection receipt — full-width below the grid.
            The rail variant lives in the right rail; both render the same
            store, so you can pick whichever feels best and remove the other. */}
        <PredetectionReceipt variant="inline" />

        {/* Full-width log feed */}
        <Card>
          <ForensicLogViewer />
        </Card>
      </div>

      {/* Right rail — sticky predetection toast stack. Hidden below
          1600px viewport so the inline receipt below the grid is the
          single canonical view at narrower widths and the rail header
          doesn't get clipped (main column is min-w-1280, rail wants
          ~280px). */}
      <aside className="w-[280px] shrink-0 hidden 2xl:block">
        <div className="sticky top-4">
          <PredetectionReceipt variant="rail" />
        </div>
      </aside>
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
