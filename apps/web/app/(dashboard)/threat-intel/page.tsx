"use client"

import { useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { useIocSearch } from "@/lib/api/threat-intel"
import { MitreCoverageMatrix } from "@/components/threat-intel/mitre-coverage-matrix"
import { ObservableLink } from "@/components/intel/observable-drawer"
import { openObservable } from "@/lib/observable-store"
import { downloadCsv } from "@/lib/download"
import { toast } from "@/lib/toast"
import {
  Search,
  Shield,
  Globe,
  Mail,
  Hash,
  Server,
  AlertTriangle,
  CheckCircle,
  HelpCircle,
  Eye,
  ExternalLink,
  Filter,
  Download,
} from "lucide-react"
import { cn } from "@/lib/utils"

const reputationConfig: Record<string, { color: string; bg: string; icon: typeof Shield }> = {
  malicious: { color: "text-red-500", bg: "bg-red-500/10", icon: AlertTriangle },
  suspicious: { color: "text-amber-500", bg: "bg-amber-500/10", icon: Eye },
  clean: { color: "text-emerald-500", bg: "bg-emerald-500/10", icon: CheckCircle },
  unknown: { color: "text-gray-400", bg: "bg-gray-500/10", icon: HelpCircle },
}

const typeIcons: Record<string, typeof Globe> = {
  ip: Server,
  domain: Globe,
  email: Mail,
  hash: Hash,
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—"
  const dt = Date.parse(iso)
  if (Number.isNaN(dt)) return iso
  const seconds = Math.max(0, (Date.now() - dt) / 1000)
  if (seconds < 60) return `${Math.floor(seconds)}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

type TabId = "ioc" | "mitre"

export default function ThreatIntelPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const tabParam = searchParams?.get("tab")
  const initialTab: TabId = tabParam === "mitre" ? "mitre" : "ioc"
  const [tab, setTab] = useState<TabId>(initialTab)
  const onTabChange = (next: TabId) => {
    setTab(next)
    const sp = new URLSearchParams(searchParams?.toString() ?? "")
    if (next === "ioc") sp.delete("tab")
    else sp.set("tab", next)
    const qs = sp.toString()
    router.replace(qs ? `?${qs}` : "?", { scroll: false })
  }

  const [iocQuery, setIocQuery] = useState("")
  const iocs = useIocSearch({ q: iocQuery || undefined, limit: 20 })
  // Reputation filter — multi-select. Empty = show all.
  const [filterOpen, setFilterOpen] = useState(false)
  const [reputationFilter, setReputationFilter] = useState<Set<string>>(new Set())

  // Project the API IocItem shape into the existing JSX's expected fields.
  const iocEntries = useMemo(
    () => {
      const all = (iocs.data?.items ?? []).map((item) => ({
        type: item.type,
        indicator: item.indicator,
        source: item.source,
        reputation: item.reputation,
        timestamp: timeAgo(item.lastChecked),
      }))
      if (reputationFilter.size === 0) return all
      return all.filter((e) => reputationFilter.has(e.reputation))
    },
    [iocs.data, reputationFilter],
  )

  const onExport = () => {
    if (iocEntries.length === 0) {
      toast.warning("Nothing to export — IOC list is empty.")
      return
    }
    const stamp = new Date().toISOString().replace(/[:.]/g, "-")
    downloadCsv(`strix-iocs-${stamp}.csv`, iocEntries as unknown as Record<string, unknown>[])
    toast.success(`Exported ${iocEntries.length} IOCs.`)
  }

  const toggleReputation = (rep: string) => {
    setReputationFilter((prev) => {
      const next = new Set(prev)
      if (next.has(rep)) next.delete(rep)
      else next.add(rep)
      return next
    })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] text-strix-primary dark:text-strix-cyan uppercase tracking-widest font-semibold mb-1">
            THREAT INTELLIGENCE
          </p>
          <h1 className="text-3xl font-black text-[var(--strix-text)] tracking-tight">
            Reputation Core &<br />
            Exposure Tracking
          </h1>
        </div>
        <div className="flex items-center gap-2 relative">
          <button
            onClick={() => setFilterOpen((v) => !v)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-semibold uppercase tracking-wider border border-[var(--strix-border)] hover:bg-[var(--strix-bg-surface)] transition-colors",
              reputationFilter.size > 0
                ? "text-strix-primary dark:text-strix-cyan border-strix-cyan/40"
                : "text-[var(--strix-text-muted)]"
            )}
          >
            <Filter className="h-3.5 w-3.5" />
            Filters {reputationFilter.size > 0 && `(${reputationFilter.size})`}
          </button>
          <button
            onClick={onExport}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-semibold uppercase tracking-wider border border-[var(--strix-border)] text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-surface)] transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            Export CSV
          </button>
          {filterOpen && (
            <div className="absolute right-0 top-12 z-20 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-lg shadow-xl p-3 min-w-[220px]">
              <div className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)] mb-2">Reputation</div>
              {(["malicious", "suspicious", "clean", "unknown"] as const).map((r) => (
                <label key={r} className="flex items-center gap-2 py-1 cursor-pointer text-[11px] text-[var(--strix-text)]">
                  <input
                    type="checkbox"
                    checked={reputationFilter.has(r)}
                    onChange={() => toggleReputation(r)}
                  />
                  <span className="capitalize">{r}</span>
                </label>
              ))}
              <button
                onClick={() => { setReputationFilter(new Set()); setFilterOpen(false) }}
                className="mt-2 text-[10px] text-strix-cyan hover:underline"
              >
                Clear filters
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Tabs — IOC registry vs. ATT&CK Coverage Matrix. Default = IOC. */}
      <div data-tour="ti-tabs" className="flex items-center gap-1 border-b border-[var(--strix-border)]">
        {(["ioc", "mitre"] as const).map((t) => {
          const active = tab === t
          const label = t === "ioc" ? "IOC Registry" : "ATT&CK Coverage"
          return (
            <button
              key={t}
              type="button"
              onClick={() => onTabChange(t)}
              className={
                "relative px-4 py-2 text-[11px] uppercase tracking-wider font-semibold transition-colors " +
                (active
                  ? "text-[var(--strix-text)]"
                  : "text-[var(--strix-text-muted)] hover:text-[var(--strix-text)]")
              }
            >
              {label}
              {active && (
                <span className="absolute left-2 right-2 -bottom-px h-0.5 bg-strix-primary dark:bg-strix-cyan rounded-t" />
              )}
            </button>
          )
        })}
      </div>

      {tab === "mitre" ? (
        <MitreCoverageMatrix />
      ) : (
      <>
      {/* Reputation Core - IOC Table */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">
              Reputation Core — IOC Registry
            </h3>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
              <input
                type="text"
                value={iocQuery}
                onChange={(e) => setIocQuery(e.target.value)}
                placeholder="Search or paste indicator (email/IP/domain/hash)…"
                className="pl-9 pr-4 py-1.5 rounded-lg text-xs bg-[var(--strix-bg-surface)] border border-[var(--strix-border)] text-[var(--strix-text)] placeholder:text-[var(--strix-text-muted)] focus:outline-none focus:ring-1 focus:ring-strix-primary dark:focus:ring-strix-cyan w-[280px]"
              />
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-lg border border-[var(--strix-border)]">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-[var(--strix-bg-surface)]">
                <th className="text-left py-2.5 px-4 text-[9px] font-bold text-[var(--strix-text-muted)] uppercase tracking-wider">Type</th>
                <th className="text-left py-2.5 px-4 text-[9px] font-bold text-[var(--strix-text-muted)] uppercase tracking-wider">Indicator</th>
                <th className="text-left py-2.5 px-4 text-[9px] font-bold text-[var(--strix-text-muted)] uppercase tracking-wider">Source</th>
                <th className="text-left py-2.5 px-4 text-[9px] font-bold text-[var(--strix-text-muted)] uppercase tracking-wider">Reputation</th>
                <th className="text-left py-2.5 px-4 text-[9px] font-bold text-[var(--strix-text-muted)] uppercase tracking-wider">Timestamp</th>
                <th className="text-left py-2.5 px-4 text-[9px] font-bold text-[var(--strix-text-muted)] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--strix-border)]">
              {iocEntries.map((entry, i) => {
                const TypeIcon = typeIcons[entry.type] || Globe
                const repConfig = reputationConfig[entry.reputation]
                const RepIcon = repConfig.icon
                return (
                  <tr
                    key={i}
                    onClick={() => openObservable(entry.indicator)}
                    className="hover:bg-[var(--strix-bg-surface)] transition-colors cursor-pointer"
                  >
                    <td className="py-3 px-4">
                      <TypeIcon className="h-4 w-4 text-[var(--strix-text-muted)]" />
                    </td>
                    <td className="py-3 px-4">
                      <ObservableLink
                        value={entry.indicator}
                        className="font-mono font-semibold text-[var(--strix-text)] hover:text-strix-cyan"
                      />
                    </td>
                    <td className="py-3 px-4 text-[var(--strix-text-muted)]">{entry.source}</td>
                    <td className="py-3 px-4">
                      <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase", repConfig.bg, repConfig.color)}>
                        <RepIcon className="h-3 w-3" />
                        {entry.reputation}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-[var(--strix-text-muted)] font-mono text-[10px]">{entry.timestamp}</td>
                    <td className="py-3 px-4">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          openObservable(entry.indicator)
                        }}
                        className="text-strix-primary dark:text-strix-cyan hover:underline text-[10px] font-semibold flex items-center gap-1"
                      >
                        Investigate <ExternalLink className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      </>
      )}
    </div>
  )
}
