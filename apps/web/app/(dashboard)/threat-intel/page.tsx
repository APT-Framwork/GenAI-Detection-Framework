"use client"

import { useMemo, useState } from "react"
import { useRouter } from "next/navigation"

import {
  useCompromisedAssets,
  useFileScan,
  useIocSearch,
} from "@/lib/api/threat-intel"
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
  TrendingUp,
  Eye,
  ExternalLink,
  Filter,
  Download,
  Upload,
  Loader2,
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

function severityFromVae(prob: number | null): string {
  if (prob == null) return "low"
  if (prob >= 0.85) return "critical"
  if (prob >= 0.7) return "high"
  if (prob >= 0.4) return "medium"
  return "low"
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

// Each entry maps to a real backend adapter under
// apps/api/src/strix_api/adapters/. We don't have a dedicated
// /monitoring/adapters health endpoint yet, so the per-feed status is
// derived from observable signals at runtime (see useFeedStatuses
// inside the page component). The metadata below is intrinsic to the
// adapter (rate limits, source kind) and doesn't change between runs.
const FEED_REGISTRY = [
  {
    name: "XposedOrNot",
    adapterPath: "apps/api/src/strix_api/adapters/xposedornot_adapter.py",
    rate: "1 lookup / 1s",
    kind: "live",
    description: "Free email breach lookups for IOC enrichment (no API key).",
  },
  {
    name: "VirusTotal",
    adapterPath: "apps/api/src/strix_api/adapters/virustotal_adapter.py",
    rate: "4 lookups / min",
    kind: "live",
    description: "File hash + URL scan via /threat-intel/virustotal/scan.",
  },
  {
    name: "MITRE ATT&CK",
    adapterPath: "static reference set",
    rate: "static",
    kind: "static",
    description: "Tactic/technique catalogue loaded at boot.",
  },
  {
    name: "Anthropic LLM",
    adapterPath: "apps/api/src/strix_api/adapters/llm_adapter.py",
    rate: "Opus + Haiku",
    kind: "live",
    description: "LLM-assisted IOC summarisation (Anthropic Messages API).",
  },
] as const

export default function ThreatIntelPage() {
  const router = useRouter()
  const [iocQuery, setIocQuery] = useState("")
  const iocs = useIocSearch({ q: iocQuery || undefined, limit: 20 })
  const compromised = useCompromisedAssets(20)
  const fileScan = useFileScan()
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

  // Project compromised assets to the existing card layout.
  const compromisedAssets = useMemo(
    () =>
      (compromised.data?.items ?? []).map((a) => ({
        hostname: a.agentName ?? a.hostId.slice(0, 8),
        ip: a.ipAddress ?? "—",
        vector:
          a.maxVaeProb != null
            ? `VAE ${Math.round(a.maxVaeProb * 100)}% · GNN ${
                a.maxGnnRisk != null ? Math.round(a.maxGnnRisk * 100) : "—"
              }%`
            : "—",
        severity: severityFromVae(a.maxVaeProb ?? null),
        lastSeen: timeAgo(a.lastDetectionAt ?? a.lastSeenAt),
      })),
    [compromised.data],
  )

  // 4-bucket regional intensity now derived from VAE distribution.
  const threatIntensity = useMemo(() => {
    const items = compromised.data?.items ?? []
    const buckets = [0, 0, 0, 0]
    for (const it of items) {
      const p = it.maxVaeProb ?? 0
      const bucket = p >= 0.7 ? 0 : p >= 0.4 ? 1 : p >= 0.2 ? 2 : 3
      buckets[bucket] += 1
    }
    const total = items.length || 1
    return [
      { region: "Critical hosts", value: Math.round((buckets[0] / total) * 100), trend: `${buckets[0]} hosts` },
      { region: "High",           value: Math.round((buckets[1] / total) * 100), trend: `${buckets[1]} hosts` },
      { region: "Medium",         value: Math.round((buckets[2] / total) * 100), trend: `${buckets[2]} hosts` },
      { region: "Low",            value: Math.round((buckets[3] / total) * 100), trend: `${buckets[3]} hosts` },
    ]
  }, [compromised.data])

  const onUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) fileScan.mutate(f)
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
            <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-semibold uppercase tracking-wider border border-[var(--strix-border)] text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-surface)] cursor-pointer transition-colors">
              {fileScan.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Upload className="h-3.5 w-3.5" />
              )}
              Scan File
              <input type="file" className="hidden" onChange={onUpload} />
            </label>
          </div>
        </div>
        {fileScan.data && (
          <div className="mb-3 px-3 py-2 rounded-lg bg-[var(--strix-bg-surface)] border border-[var(--strix-border)] text-[10px] text-[var(--strix-text-muted)]">
            <span className="font-bold text-[var(--strix-text)]">{fileScan.data.filename}</span>
            {" · "}sha256 {fileScan.data.sha256.slice(0, 12)}…
            {" · "}status {fileScan.data.status}
          </div>
        )}

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
                  <tr key={i} className="hover:bg-[var(--strix-bg-surface)] transition-colors">
                    <td className="py-3 px-4">
                      <TypeIcon className="h-4 w-4 text-[var(--strix-text-muted)]" />
                    </td>
                    <td className="py-3 px-4">
                      <span className="font-mono font-semibold text-[var(--strix-text)]">
                        {entry.indicator}
                      </span>
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
                        onClick={() => {
                          // Use the indicator as the search query on the
                          // attack-analysis "latest" view — at minimum it
                          // gets the operator to a context where the IOC
                          // can be cross-referenced. No dedicated IOC
                          // detail route exists yet.
                          router.push(`/attack-analysis/latest?q=${encodeURIComponent(entry.indicator)}`)
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

      {/* Middle Row: Compromised Assets + Breach Feeds */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Compromised Assets */}
        <div className="lg:col-span-7 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">
              Compromised Assets
            </h3>
            <span className="ml-auto text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider">
              Live · Auto-refresh
            </span>
          </div>

          <div className="space-y-2">
            {compromisedAssets.map((asset, i) => (
              <div
                key={i}
                className={cn(
                  "flex items-center gap-4 p-3 rounded-lg border transition-colors",
                  asset.severity === "critical"
                    ? "bg-red-500/5 border-red-500/20"
                    : asset.severity === "high"
                    ? "bg-amber-500/5 border-amber-500/20"
                    : "bg-[var(--strix-bg-surface)] border-[var(--strix-border)]"
                )}
              >
                <div className={cn(
                  "h-2 w-2 rounded-full flex-shrink-0",
                  asset.severity === "critical" && "bg-red-500 animate-pulse",
                  asset.severity === "high" && "bg-amber-500",
                  asset.severity === "medium" && "bg-yellow-500"
                )} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs font-bold text-[var(--strix-text)]">{asset.hostname}</span>
                    <span className="text-[10px] font-mono text-[var(--strix-text-muted)]">{asset.ip}</span>
                  </div>
                  <span className="text-[10px] text-[var(--strix-text-muted)]">{asset.vector}</span>
                </div>
                <span className={cn(
                  "text-[9px] font-bold uppercase px-2 py-0.5 rounded-full",
                  asset.severity === "critical" && "bg-red-500/10 text-red-500",
                  asset.severity === "high" && "bg-amber-500/10 text-amber-500",
                  asset.severity === "medium" && "bg-yellow-500/10 text-yellow-500"
                )}>
                  {asset.severity}
                </span>
                <span className="text-[10px] text-[var(--strix-text-muted)] flex-shrink-0">{asset.lastSeen}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Breach Feed Integrations */}
        <div className="lg:col-span-5 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Globe className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">
              Breach Feed Integrations
            </h3>
          </div>

          <div className="space-y-3">
            {FEED_REGISTRY.map((feed) => {
              // We mark a feed "online" when:
              //   * static adapter (MITRE) — always online once loaded
              //   * IOC search query has returned for XposedOrNot/VT
              //     (their results contribute to the IOC table)
              //   * file scan has succeeded for VT
              // If iocs.isError we fall back to "degraded" so the
              // pill is honest about connection problems.
              const usedByIocSearch = feed.name === "XposedOrNot" || feed.name === "VirusTotal"
              const status: "online" | "static" | "degraded" | "idle" =
                feed.kind === "static"
                  ? "static"
                  : iocs.isError
                  ? "degraded"
                  : usedByIocSearch && iocs.isFetched
                  ? "online"
                  : "idle"
              const dotCls =
                status === "online"   ? "bg-emerald-500" :
                status === "static"   ? "bg-cyan-500"    :
                status === "degraded" ? "bg-rose-500"    : "bg-[#497f8b]"
              const labelCls =
                status === "online"   ? "text-emerald-500" :
                status === "static"   ? "text-cyan-500"    :
                status === "degraded" ? "text-rose-500"    : "text-[#497f8b]"
              return (
                <div key={feed.name} className="flex items-center gap-3 p-3 rounded-lg bg-[var(--strix-bg-surface)] border border-[var(--strix-border)]" title={feed.description}>
                  <div className={cn("h-2 w-2 rounded-full flex-shrink-0", dotCls)} />
                  <div className="flex-1">
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs font-bold text-[var(--strix-text)]">{feed.name}</span>
                      <span className="text-[10px] font-mono text-[var(--strix-text-muted)]">{feed.rate}</span>
                    </div>
                    <div className="flex items-center justify-between mt-0.5 gap-2">
                      <span className={cn("text-[9px] font-semibold uppercase", labelCls)}>
                        {status}
                      </span>
                      <span className="text-[10px] text-[var(--strix-text-muted)] font-mono truncate">
                        {feed.adapterPath}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Threat Intensity by Region */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
          <h3 className="text-sm font-bold text-[var(--strix-text)]">
            Global Threat Intensity
          </h3>
          <span className="ml-auto text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider">
            Last 24 hours
          </span>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {threatIntensity.map((region, i) => (
            <div key={i} className="p-4 rounded-xl bg-[var(--strix-bg-surface)] border border-[var(--strix-border)]">
              <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-2">
                {region.region}
              </span>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-2xl font-bold text-[var(--strix-text)]">{region.value}%</span>
                <span className="text-[10px] text-red-500 font-medium">{region.trend}</span>
              </div>
              {/* Intensity Bar */}
              <div className="h-1.5 rounded-full bg-[var(--strix-border)] overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-500",
                    region.value >= 80 ? "bg-red-500" : region.value >= 60 ? "bg-amber-500" : "bg-emerald-500"
                  )}
                  style={{ width: `${region.value}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
