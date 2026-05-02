"use client"

// affected-hosts-table.tsx — per-host breakdown of a single chain.
// Surfaces data from /analysis/chains/{id}/infection that doesn't appear
// anywhere on the dashboard. Each row links into the Threat Intel page
// with the hostname pre-filtered.

import type { InfectedHost } from "@/lib/api/analysis"
import { cn } from "@/lib/utils"
import Link from "next/link"
import { ExternalLink } from "lucide-react"

interface AffectedHostsTableProps {
  hosts: InfectedHost[]
  className?: string
}

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

function severityFromStage(stage: number | null): { label: string; cls: string } {
  if (stage == null || stage <= 0) return { label: "—", cls: "text-[#497f8b] bg-[#497f8b]/10" }
  if (stage >= 6) return { label: "Critical", cls: "text-rose-600 dark:text-rose-400 bg-rose-500/10" }
  if (stage >= 4) return { label: "High", cls: "text-amber-600 dark:text-amber-400 bg-amber-500/10" }
  if (stage >= 2) return { label: "Medium", cls: "text-yellow-600 dark:text-yellow-400 bg-yellow-500/10" }
  return { label: "Low", cls: "text-cyan-600 dark:text-cyan-400 bg-cyan-500/10" }
}

export function AffectedHostsTable({ hosts, className }: AffectedHostsTableProps) {
  if (hosts.length === 0) {
    return (
      <div className={cn("rounded-xl border border-dashed border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] py-8 text-center text-xs text-[#497f8b] dark:text-[var(--strix-text-muted)]", className)}>
        No affected hosts recorded for this chain.
      </div>
    )
  }

  return (
    <div className={cn("overflow-hidden rounded-lg border border-[var(--strix-border)]", className)}>
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-[var(--strix-bg-surface)]">
            <Th>Host</Th>
            <Th>First Seen</Th>
            <Th>Reached Stage</Th>
            <Th>Severity</Th>
            <Th>Action</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--strix-border)]">
          {hosts.map((h) => {
            const sev = severityFromStage(h.currentStage)
            return (
              <tr key={h.hostId} className="hover:bg-[var(--strix-bg-surface)] transition-colors">
                <td className="py-2.5 px-4">
                  <div className="font-mono font-semibold text-[var(--strix-text)]">
                    {h.hostName || h.hostId.slice(0, 12)}
                  </div>
                  <div className="text-[10px] text-[var(--strix-text-muted)] font-mono">
                    {h.hostId.length > 12 ? h.hostId.slice(0, 12) + "…" : h.hostId}
                  </div>
                </td>
                <td className="py-2.5 px-4 text-[var(--strix-text-muted)] font-mono text-[10px]">
                  {fmt(h.firstSeen)}
                </td>
                <td className="py-2.5 px-4 text-[var(--strix-text)]">
                  {h.currentStageName ? (
                    <>
                      <span className="font-mono text-[10px] text-[var(--strix-text-muted)] mr-1.5">
                        {h.currentStage}
                      </span>
                      {h.currentStageName}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="py-2.5 px-4">
                  <span className={cn("inline-flex px-2 py-0.5 rounded-full text-[9px] font-bold uppercase", sev.cls)}>
                    {sev.label}
                  </span>
                </td>
                <td className="py-2.5 px-4">
                  <Link
                    href={`/threat-intel?q=${encodeURIComponent(h.hostName || h.hostId)}`}
                    className="text-strix-primary dark:text-strix-cyan hover:underline text-[10px] font-semibold flex items-center gap-1"
                  >
                    Investigate <ExternalLink className="h-3 w-3" />
                  </Link>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="text-left py-2.5 px-4 text-[9px] font-bold text-[var(--strix-text-muted)] uppercase tracking-wider">
      {children}
    </th>
  )
}
