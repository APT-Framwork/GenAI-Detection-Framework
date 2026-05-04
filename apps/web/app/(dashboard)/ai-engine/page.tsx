"use client"

import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { apiFetch } from "@/lib/api/client"
import { useLiveFeed } from "@/lib/api/live-feed"
import { CircularProgress } from "@/components/charts/circular-progress"
import { cn } from "@/lib/utils"
import { MODEL_REGISTRY, compositeMetrics, type ModelMetrics } from "@/lib/model-registry"
import {
  Brain,
  Activity,
  Gauge,
  Clock,
  Zap,
  TrendingUp,
  BarChart3,
  Cpu,
  Terminal,
} from "lucide-react"

interface ModelHealth {
  name: string
  version: string
  weightsSha256: string
  status: string
  driftKl?: number | null
}
interface ModelsResponse { models: ModelHealth[] }
interface TrendPoint {
  ts: string
  aeAnomaly: number
  vaeProb: number
  transformerConfidence: number
  gnnRisk: number
}
interface ConfidenceTrendResponse { window: string; points: TrendPoint[] }

const COLOR_TINTS: Record<ModelMetrics["color"], { fg: string; bg: string; border: string }> = {
  cyan:    { fg: "text-strix-primary dark:text-strix-cyan", bg: "bg-strix-primary/10 dark:bg-strix-cyan/10", border: "border-strix-primary/20 dark:border-strix-cyan/20" },
  purple:  { fg: "text-purple-500",  bg: "bg-purple-500/10",  border: "border-purple-500/20" },
  amber:   { fg: "text-amber-500",   bg: "bg-amber-500/10",   border: "border-amber-500/20" },
  emerald: { fg: "text-emerald-500", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  blue:    { fg: "text-blue-500",    bg: "bg-blue-500/10",    border: "border-blue-500/20" },
}

export default function AiEnginePage() {
  const models = useQuery({
    queryKey: ["monitoring", "models"],
    queryFn: () => apiFetch<ModelsResponse>("/monitoring/models"),
    refetchInterval: 30_000,
  })
  const trend = useQuery({
    queryKey: ["monitoring", "confidence-trend", "7d"],
    queryFn: () => apiFetch<ConfidenceTrendResponse>("/monitoring/confidence-trend?window=7d"),
    refetchInterval: 60_000,
  })
  // Bump retained events so the panel can show real history (backfilled
  // from `/streams/live-feed/recent` on mount) and serve the Export buttons.
  const liveFeed = useLiveFeed({ maxEvents: 500, backfillLimit: 200 })
  const [showAll, setShowAll] = useState(false)
  const [expandedModel, setExpandedModel] = useState<string | null>(null)

  // Composite metrics come from the registry — these are training-time
  // eval numbers and don't depend on live signals. The previous code
  // computed accuracy as `(1 - avgDrift)` which was always 100% when
  // /monitoring/models returned null drift values.
  const composite = compositeMetrics()

  // Live throughput: events per minute over the SSE feed. We count
  // events whose `occurredAt` falls in the last 60 seconds — that's
  // already a per-minute rate, no division required. The previous
  // implementation divided by the timestamp span, which exploded to
  // hundreds of thousands when the buffer happened to contain a
  // sub-second burst.
  const throughputPerMin = useMemo(() => {
    const xs = liveFeed.events
    if (xs.length === 0) return null
    const cutoff = Date.now() - 60_000
    const recent = xs.filter((e) => {
      const ts = Date.parse(e.data.occurredAt)
      return Number.isFinite(ts) && ts >= cutoff
    }).length
    return recent
  }, [liveFeed.events])

  // Drift signal — average KL across reported live models. Real value
  // (or null when /monitoring/models hasn't reported drift yet).
  const avgDriftKl = useMemo(() => {
    const xs = (models.data?.models ?? [])
      .map((m) => m.driftKl)
      .filter((v): v is number => typeof v === "number")
    if (xs.length === 0) return null
    return xs.reduce((a, b) => a + b, 0) / xs.length
  }, [models.data])

  const overallHealth: "optimal" | "degraded" | "unknown" = useMemo(() => {
    if (avgDriftKl == null) return "unknown"
    return avgDriftKl < 0.2 ? "optimal" : "degraded"
  }, [avgDriftKl])

  const modelConfidenceData = useMemo(
    () =>
      (trend.data?.points ?? []).map((p) => ({
        time: new Date(p.ts).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        classifier: Math.round(p.transformerConfidence * 100),
        gnn: Math.round(p.gnnRisk * 100),
        vae: Math.round(p.vaeProb * 100),
      })),
    [trend.data],
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] text-strix-primary dark:text-strix-cyan uppercase tracking-widest font-semibold mb-1">
            AI ENGINE
          </p>
          <h1 className="text-3xl font-black text-[var(--strix-text)] tracking-tight">
            Model Performance<br />
            & Telemetry
          </h1>
          <p className="text-[11px] text-[var(--strix-text-muted)] mt-2 max-w-[640px] leading-relaxed">
            Test-set metrics below are training-time evaluation numbers from the artefacts under{" "}
            <span className="font-mono text-[10px]">apps/notebooks/</span> and{" "}
            <span className="font-mono text-[10px]">RL_agent/evaluation/</span>. Live signals (drift KL,
            inference rate) are sourced from the API and refresh every 30 s.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
              Engine Health
            </span>
            <span className={cn(
              "inline-block px-3 py-1 rounded-md text-xs font-bold border uppercase",
              overallHealth === "optimal"  && "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
              overallHealth === "degraded" && "bg-amber-500/10  text-amber-500  border-amber-500/20",
              overallHealth === "unknown"  && "bg-[#497f8b]/10  text-[#497f8b]  border-[#497f8b]/20",
            )}>
              {overallHealth}
            </span>
          </div>
        </div>
      </div>

      {/* Top KPI Row — composite test-set metrics + live signals. */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi
          icon={Gauge}
          label="Composite Accuracy"
          value={`${composite.accuracyPct}%`}
          sub={`${composite.modelCount} models · test set`}
        />
        <Kpi
          icon={BarChart3}
          label="Composite F1"
          value={composite.f1.toFixed(3)}
          sub="harmonic mean across models"
        />
        <Kpi
          icon={Zap}
          label="Throughput"
          value={throughputPerMin == null ? "—" : `${throughputPerMin}/min`}
          sub={`SSE feed ${liveFeed.status}`}
        />
        <Kpi
          icon={Clock}
          label="Avg Drift KL"
          value={avgDriftKl == null ? "—" : avgDriftKl.toFixed(4)}
          sub={avgDriftKl == null ? "no live drift signal" : avgDriftKl < 0.2 ? "in-distribution" : "shift detected"}
        />
      </div>

      {/* Model Cards + Composite gauge */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8 space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <Brain className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">Active Models</h3>
            <span className="text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider">
              metrics from training notebooks · click for details
            </span>
          </div>
          {MODEL_REGISTRY.map((m) => {
            const isOpen = expandedModel === m.name
            const tint = COLOR_TINTS[m.color]
            const live = (models.data?.models ?? []).find((lm) =>
              lm.name.toLowerCase().includes(m.name.toLowerCase().split(" ")[0]),
            )
            return (
              <div key={m.name} className={cn("bg-[var(--strix-bg-card)] border rounded-xl p-5", tint.border)}>
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={cn("p-2 rounded-lg", tint.bg)}>
                      <Cpu className={cn("h-4 w-4", tint.fg)} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-baseline gap-2 flex-wrap">
                        <h4 className="text-sm font-bold text-[var(--strix-text)] truncate">{m.name}</h4>
                        <span className="text-[10px] font-mono text-[var(--strix-text-muted)]">{m.version}</span>
                      </div>
                      <span className={cn(
                        "text-[9px] font-bold uppercase tracking-wider",
                        m.status === "active" ? "text-emerald-500" : "text-amber-500"
                      )}>
                        {m.status}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-6 shrink-0">
                    <Metric label="Acc" value={pct(m.metrics.accuracy)} />
                    <Metric label="F1"  value={fixed(m.metrics.f1)} />
                    <Metric label="AUC" value={fixed(m.metrics.auc)} />
                    <button
                      onClick={() => setExpandedModel(isOpen ? null : m.name)}
                      className={cn("text-[10px] font-semibold hover:underline", tint.fg)}
                    >
                      {isOpen ? "Hide ↑" : "View Details →"}
                    </button>
                  </div>
                </div>
                {isOpen && (
                  <div className="mt-4 pt-4 border-t border-[var(--strix-border)] space-y-3">
                    <p className="text-[11px] text-[var(--strix-text-muted)] leading-relaxed">
                      {m.description}
                    </p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <Detail label="Architecture" value={m.architecture} />
                      <Detail label="Precision" value={pct(m.metrics.precision)} />
                      <Detail label="Recall" value={pct(m.metrics.recall)} />
                      <Detail label="Threshold" value={m.metrics.threshold != null ? m.metrics.threshold.toFixed(4) : "—"} mono />
                      {(m.metrics.extras ?? []).map((e) => (
                        <Detail key={e.label} label={e.label} value={e.value} />
                      ))}
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 pt-2 border-t border-dashed border-[var(--strix-border)]">
                      <Detail label="Live status" value={live?.status ?? "—"} />
                      <Detail label="Drift KL" value={live?.driftKl?.toFixed(4) ?? "—"} />
                      <Detail
                        label="Weights SHA-256"
                        value={live?.weightsSha256 ? live.weightsSha256.slice(0, 12) + "…" : "—"}
                        mono
                      />
                    </div>
                    <p className="text-[10px] text-[var(--strix-text-muted)] leading-relaxed pt-1">
                      Source: <span className="font-mono">{m.source}</span>
                    </p>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Composite gauge — uses real composite test-set accuracy. */}
        <div className="lg:col-span-4 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5 flex flex-col items-center justify-center">
          <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-widest mb-4">
            Composite Test-Set Accuracy
          </span>
          <CircularProgress value={composite.accuracyPct} size={180} strokeWidth={12} />
          <div className="mt-4 text-center">
            <span className="text-[10px] text-[var(--strix-text-muted)]">
              mean over {composite.modelCount} models that report accuracy
            </span>
          </div>
        </div>
      </div>

      {/* Confidence Trend Chart */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">
              Confidence Trend (7-Day)
            </h3>
          </div>
          <div className="flex items-center gap-4">
            <Legend color="#006B94" darkColor="#00F2FF" label="Transformer" />
            <Legend color="#8B5CF6" label="GNN" />
            <Legend color="#F59E0B" label="VAE" />
          </div>
        </div>

        {modelConfidenceData.length === 0 ? (
          <div className="h-[200px] flex items-center justify-center text-[11px] text-[var(--strix-text-muted)] italic">
            No trend points returned by /monitoring/confidence-trend yet — run a simulation to populate.
          </div>
        ) : (
          <div className="relative h-[200px] w-full">
            <svg className="w-full h-full" viewBox="0 0 600 200" preserveAspectRatio="none">
              {[0, 1, 2, 3, 4].map((i) => (
                <line key={`grid-${i}`} x1="0" y1={i * 50} x2="600" y2={i * 50} stroke="var(--strix-border)" strokeWidth="0.5" opacity="0.5" />
              ))}
              <Trendline points={modelConfidenceData.map((d) => d.classifier)} stroke="#006B94" />
              <Trendline points={modelConfidenceData.map((d) => d.gnn)} stroke="#8B5CF6" />
              <Trendline points={modelConfidenceData.map((d) => d.vae)} stroke="#F59E0B" />
            </svg>
            <div className="flex justify-between mt-2">
              {modelConfidenceData.map((d, i) => (
                <span key={i} className="text-[9px] text-[var(--strix-text-muted)] font-mono">{d.time}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Live Inference Stream */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Terminal className="h-4 w-4 text-[var(--strix-text-muted)]" />
          <h3 className="text-sm font-bold text-[var(--strix-text)]">
            Live Inference Stream
          </h3>
          <span className="text-[10px] text-[var(--strix-text-muted)] tabular-nums">
            · {liveFeed.events.length} verdict{liveFeed.events.length === 1 ? "" : "s"} retained
          </span>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              disabled={liveFeed.events.length === 0}
              className="text-[10px] uppercase tracking-wider px-2 py-1 rounded border border-[var(--strix-border)] hover:bg-[var(--strix-bg-surface)] disabled:opacity-40 disabled:cursor-not-allowed text-[var(--strix-text-muted)]"
            >
              {showAll ? "Collapse" : "View all"}
            </button>
            <button
              type="button"
              onClick={() => downloadInferenceJson(liveFeed.events)}
              disabled={liveFeed.events.length === 0}
              className="text-[10px] uppercase tracking-wider px-2 py-1 rounded border border-[var(--strix-border)] hover:bg-[var(--strix-bg-surface)] disabled:opacity-40 disabled:cursor-not-allowed text-[var(--strix-text-muted)]"
            >
              Export JSON
            </button>
            <button
              type="button"
              onClick={() => downloadInferenceCsv(liveFeed.events)}
              disabled={liveFeed.events.length === 0}
              className="text-[10px] uppercase tracking-wider px-2 py-1 rounded border border-[var(--strix-border)] hover:bg-[var(--strix-bg-surface)] disabled:opacity-40 disabled:cursor-not-allowed text-[var(--strix-text-muted)]"
            >
              Export CSV
            </button>
            <span className={cn(
              "text-[9px] font-semibold uppercase tracking-wider flex items-center gap-1 ml-2",
              liveFeed.status === "open" ? "text-emerald-500" : "text-amber-500"
            )}>
              <Activity className="h-3 w-3" />
              {liveFeed.status}
            </span>
          </div>
        </div>

        <div className="bg-[#0D1117] dark:bg-[#080C14] rounded-xl border border-[#1E293B] overflow-hidden">
          <div className="flex items-center gap-1.5 px-4 py-2 border-b border-[#1E293B]">
            <div className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
            <div className="h-2.5 w-2.5 rounded-full bg-amber-500/70" />
            <div className="h-2.5 w-2.5 rounded-full bg-emerald-500/70" />
            <span className="text-[9px] text-gray-500 ml-2 font-mono">strix:sse:live-feed</span>
          </div>
          <div
            className={cn(
              "p-4 overflow-y-auto scrollbar-thin font-mono text-[11px] leading-6 space-y-0.5",
              showAll ? "max-h-[640px]" : "max-h-[280px]",
            )}
          >
            {liveFeed.events.length === 0 ? (
              <div className="px-2 py-1 text-gray-500">
                Waiting for verdicts… (SSE: {liveFeed.status})
              </div>
            ) : (
              liveFeed.events.map((e) => {
                const isHigh = e.data.ckcStage >= 4
                return (
                  <div key={e.id} className="flex gap-3 px-2 py-0.5 rounded hover:bg-white/5 transition-colors">
                    <span className="text-gray-500 flex-shrink-0">
                      {new Date(e.data.occurredAt).toLocaleTimeString()}
                    </span>
                    <span className={cn(
                      "font-bold flex-shrink-0 min-w-[40px]",
                      isHigh ? "text-amber-400" : "text-cyan-400",
                    )}>
                      {isHigh ? "ATTK" : "INFO"}
                    </span>
                    <span className="text-gray-300">
                      {e.data.ckcStageName} · agent {e.data.agentId ?? "—"} ·
                      {" "}AE {e.data.aeAnomalyScore != null ? e.data.aeAnomalyScore.toFixed(3) : "—"}
                      {" "}· VAE {e.data.vaeMaliciousProb != null ? (e.data.vaeMaliciousProb * 100).toFixed(0) : "—"}%
                      {" "}· GNN {e.data.gnnNodeRisk != null ? e.data.gnnNodeRisk.toFixed(3) : "—"}
                      {" "}· {e.data.dqnActionName ?? "MONITOR"}
                    </span>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ----------------------------------------------------------------------------
// Export helpers — proof-of-real-inference for the demo. Each row is the
// FULL verdict envelope (timestamp, agent, AE/VAE/GNN scores, DQN action,
// MITRE techniques) so you can replay exactly what the dashboard saw.
// ----------------------------------------------------------------------------

function downloadInferenceJson(
  events: ReadonlyArray<{ id: string; data: import("@/lib/api/live-feed").LiveFeedEvent; receivedAt: number }>,
) {
  const payload = {
    exportedAt: new Date().toISOString(),
    count: events.length,
    schema: "strix.live-feed.v1",
    events: events.map((e) => ({
      id: e.id,
      receivedAt: new Date(e.receivedAt).toISOString(),
      ...e.data,
    })),
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" })
  triggerDownload(blob, `strix-live-inference-${stamp()}.json`)
}

function downloadInferenceCsv(
  events: ReadonlyArray<{ id: string; data: import("@/lib/api/live-feed").LiveFeedEvent; receivedAt: number }>,
) {
  const headers = [
    "received_at", "occurred_at", "alert_id", "agent_id",
    "ckc_stage", "ckc_stage_name",
    "ae_anomaly_score", "vae_malicious_prob", "gnn_node_risk",
    "dqn_action", "dqn_action_name", "mitre_techniques",
  ]
  const rows = events.map((e) => [
    new Date(e.receivedAt).toISOString(),
    e.data.occurredAt,
    e.data.alertId,
    e.data.agentId ?? "",
    String(e.data.ckcStage),
    e.data.ckcStageName,
    e.data.aeAnomalyScore != null ? e.data.aeAnomalyScore.toFixed(6) : "",
    e.data.vaeMaliciousProb != null ? e.data.vaeMaliciousProb.toFixed(6) : "",
    e.data.gnnNodeRisk != null ? e.data.gnnNodeRisk.toFixed(6) : "",
    e.data.dqnAction != null ? String(e.data.dqnAction) : "",
    e.data.dqnActionName ?? "",
    (e.data.mitreTechniques ?? []).join(";"),
  ])
  const csv = [headers, ...rows].map((r) => r.map(csvCell).join(",")).join("\n")
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" })
  triggerDownload(blob, `strix-live-inference-${stamp()}.csv`)
}

function csvCell(v: string): string {
  if (/[,"\n]/.test(v)) return `"${v.replace(/"/g, '""')}"`
  return v
}

function stamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function pct(v: number | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`
}
function fixed(v: number | undefined): string {
  return v == null ? "—" : v.toFixed(3)
}

function Kpi({ icon: Icon, label, value, sub }: { icon: typeof Gauge; label: string; value: string; sub: string }) {
  return (
    <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
      <div className="flex items-center gap-1.5 mb-2">
        <Icon className="h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
        <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider">{label}</span>
      </div>
      <span className="text-2xl font-bold text-[var(--strix-text)]">{value}</span>
      <p className="text-[10px] text-[var(--strix-text-muted)] mt-1">{sub}</p>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right">
      <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block">{label}</span>
      <span className="text-base font-bold text-[var(--strix-text)]">{value}</span>
    </div>
  )
}

function Detail({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <span className="block text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)] mb-0.5">{label}</span>
      <span className={cn("text-[var(--strix-text)] font-semibold text-[12px]", mono && "font-mono text-[10px]")}>
        {value}
      </span>
    </div>
  )
}

function Legend({ color, darkColor, label }: { color: string; darkColor?: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-2 w-6 rounded-full" style={{ background: color }}>
        {darkColor && <span className="hidden dark:block h-full w-full rounded-full" style={{ background: darkColor }} />}
      </div>
      <span className="text-[9px] text-[var(--strix-text-muted)]">{label}</span>
    </div>
  )
}

function Trendline({ points, stroke }: { points: number[]; stroke: string }) {
  if (points.length === 0) return null
  const stepX = points.length > 1 ? 600 / (points.length - 1) : 0
  // Map 0..100 → 0..200 (inverted, with 10px padding top/bottom).
  const yFor = (v: number) => 190 - Math.max(0, Math.min(100, v)) * 1.8
  const d = points.map((v, i) => `${i * stepX},${yFor(v)}`).join(" ")
  return <polyline fill="none" stroke={stroke} strokeWidth="2" points={d} strokeLinejoin="round" strokeLinecap="round" />
}
