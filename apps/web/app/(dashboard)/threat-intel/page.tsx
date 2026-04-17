"use client"

import { threatIntelEntries } from "@/lib/mock-data"
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

const compromisedAssets = [
  { hostname: "WS-FIN-09", ip: "10.0.3.15", vector: "Phishing", severity: "critical", lastSeen: "2m ago" },
  { hostname: "DB-SENTINEL-02", ip: "10.0.2.5", vector: "Lateral Movement", severity: "high", lastSeen: "14m ago" },
  { hostname: "pClient_srv_01", ip: "10.0.4.22", vector: "C2 Beacon", severity: "critical", lastSeen: "3m ago" },
  { hostname: "NODE_04_02_3BV", ip: "10.0.3.15", vector: "Brute Force", severity: "medium", lastSeen: "1h ago" },
]

const breachFeeds = [
  { name: "AlienVault OTX", status: "synced", entries: "14.2k", lastSync: "2m ago" },
  { name: "VirusTotal", status: "synced", entries: "8.7k", lastSync: "5m ago" },
  { name: "AbuseIPDB", status: "synced", entries: "22.1k", lastSync: "1m ago" },
  { name: "Shodan", status: "degraded", entries: "6.3k", lastSync: "18m ago" },
]

const threatIntensity = [
  { region: "North America", value: 72, trend: "+4.2%" },
  { region: "Europe", value: 58, trend: "+1.8%" },
  { region: "Asia Pacific", value: 85, trend: "+12.1%" },
  { region: "Middle East", value: 91, trend: "+8.4%" },
]

export default function ThreatIntelPage() {
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
        <div className="flex items-center gap-2">
          <button className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-semibold uppercase tracking-wider border border-[var(--strix-border)] text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-surface)] transition-colors">
            <Filter className="h-3.5 w-3.5" />
            Filters
          </button>
          <button className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-semibold uppercase tracking-wider border border-[var(--strix-border)] text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-surface)] transition-colors">
            <Download className="h-3.5 w-3.5" />
            Export
          </button>
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
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
            <input
              type="text"
              placeholder="Search indicators..."
              className="pl-9 pr-4 py-1.5 rounded-lg text-xs bg-[var(--strix-bg-surface)] border border-[var(--strix-border)] text-[var(--strix-text)] placeholder:text-[var(--strix-text-muted)] focus:outline-none focus:ring-1 focus:ring-strix-primary dark:focus:ring-strix-cyan w-[220px]"
            />
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
              {threatIntelEntries.map((entry, i) => {
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
                      <button className="text-strix-primary dark:text-strix-cyan hover:underline text-[10px] font-semibold flex items-center gap-1">
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
            {breachFeeds.map((feed, i) => (
              <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-[var(--strix-bg-surface)] border border-[var(--strix-border)]">
                <div className={cn(
                  "h-2 w-2 rounded-full flex-shrink-0",
                  feed.status === "synced" ? "bg-emerald-500" : "bg-amber-500"
                )} />
                <div className="flex-1">
                  <div className="flex items-baseline justify-between">
                    <span className="text-xs font-bold text-[var(--strix-text)]">{feed.name}</span>
                    <span className="text-[10px] font-mono text-[var(--strix-text-muted)]">{feed.entries} entries</span>
                  </div>
                  <div className="flex items-center justify-between mt-0.5">
                    <span className={cn(
                      "text-[9px] font-semibold uppercase",
                      feed.status === "synced" ? "text-emerald-500" : "text-amber-500"
                    )}>
                      {feed.status}
                    </span>
                    <span className="text-[10px] text-[var(--strix-text-muted)]">Last sync: {feed.lastSync}</span>
                  </div>
                </div>
              </div>
            ))}
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
