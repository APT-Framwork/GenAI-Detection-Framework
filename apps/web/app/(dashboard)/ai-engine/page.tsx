"use client"

import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"

import { apiFetch } from "@/lib/api/client"
import { useLiveFeed } from "@/lib/api/live-feed"
import { CircularProgress } from "@/components/charts/circular-progress"
import { cn } from "@/lib/utils"
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

const modelCards = [
  {
    name: "GNN Classifier",
    version: "v4.2.1",
    status: "active",
    accuracy: 94.2,
    f1: 0.92,
    color: "text-strix-primary dark:text-strix-cyan",
    borderColor: "border-strix-primary/20 dark:border-strix-cyan/20",
  },
  {
    name: "VAE Anomaly",
    version: "v3.8.0",
    status: "active",
    accuracy: 89.7,
    f1: 0.87,
    color: "text-purple-500",
    borderColor: "border-purple-500/20",
  },
  {
    name: "RL Agent",
    version: "v2.1.4",
    status: "training",
    accuracy: 91.3,
    f1: 0.90,
    color: "text-amber-500",
    borderColor: "border-amber-500/20",
  },
]

const telemetryStream = [
  { time: "09:25:44", event: "Graph topology refreshed, 1,432 new edges processed", type: "info" },
  { time: "09:24:12", event: "GNN inference batch #4421 completed — 14ms avg latency", type: "info" },
  { time: "09:23:01", event: "Anomaly score threshold exceeded: subnet Alpha reconstruction error 0.012G", type: "warn" },
  { time: "09:22:18", event: "RL agent reward signal updated: +0.34 for isolation action on node-7", type: "info" },
  { time: "09:21:55", event: "VAE model checkpoint saved — epoch 142, loss: 0.0023", type: "info" },
  { time: "09:20:44", event: "Feature pipeline: 22,840 events processed in window T-5min", type: "info" },
]

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
  const liveFeed = useLiveFeed({ maxEvents: 12 })

  // Derived health snapshot for the header KPIs.
  const modelMetrics = useMemo(() => {
    const list = models.data?.models ?? []
    const driftValues = list
      .map((m) => m.driftKl)
      .filter((v): v is number => typeof v === "number")
    const avgDrift = driftValues.length
      ? driftValues.reduce((a, b) => a + b, 0) / driftValues.length
      : 0
    return {
      health:
        list.length === 0
          ? "unknown"
          : list.every((m) => m.status === "active")
          ? "optimal"
          : "degraded",
      accuracy: list.length === 0 ? 0 : Math.round((1 - avgDrift) * 100),
      f1Score: list.length === 0 ? "—" : (1 - avgDrift).toFixed(2),
      throughput: liveFeed.events.length.toString(),
      latency: liveFeed.status,
    }
  }, [models.data, liveFeed.events, liveFeed.status])

  // Trend is rendered as a sparkline via SVG `<polyline>` elements.
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
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block mb-1">
              Engine Health
            </span>
            <span className={cn(
              "inline-block px-3 py-1 rounded-md text-xs font-bold border uppercase",
              modelMetrics.health === "optimal"
                ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                : "bg-amber-500/10 text-amber-500 border-amber-500/20"
            )}>
              {modelMetrics.health}
            </span>
          </div>
        </div>
      </div>

      {/* Top Metrics Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-1.5 mb-2">
            <Gauge className="h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider">Accuracy</span>
          </div>
          <span className="text-2xl font-bold text-[var(--strix-text)]">{modelMetrics.accuracy}%</span>
        </div>
        <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-1.5 mb-2">
            <BarChart3 className="h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider">F1 Score</span>
          </div>
          <span className="text-2xl font-bold text-[var(--strix-text)]">{modelMetrics.f1Score}</span>
        </div>
        <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-1.5 mb-2">
            <Zap className="h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider">Throughput</span>
          </div>
          <span className="text-2xl font-bold text-[var(--strix-text)]">{modelMetrics.throughput}</span>
        </div>
        <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
          <div className="flex items-center gap-1.5 mb-2">
            <Clock className="h-3.5 w-3.5 text-[var(--strix-text-muted)]" />
            <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider">Avg Latency</span>
          </div>
          <span className="text-2xl font-bold text-[var(--strix-text)]">{modelMetrics.latency}</span>
        </div>
      </div>

      {/* Model Cards + Accuracy Gauge */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Model Cards */}
        <div className="lg:col-span-8 space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <Brain className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
            <h3 className="text-sm font-bold text-[var(--strix-text)]">Active Models</h3>
          </div>
          {modelCards.map((model, i) => (
            <div key={i} className={cn(
              "bg-[var(--strix-bg-card)] border rounded-xl p-5",
              model.borderColor
            )}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={cn("p-2 rounded-lg", model.name.includes("GNN") ? "bg-strix-primary/10 dark:bg-strix-cyan/10" : model.name.includes("VAE") ? "bg-purple-500/10" : "bg-amber-500/10")}>
                    <Cpu className={cn("h-4 w-4", model.color)} />
                  </div>
                  <div>
                    <div className="flex items-baseline gap-2">
                      <h4 className="text-sm font-bold text-[var(--strix-text)]">{model.name}</h4>
                      <span className="text-[10px] font-mono text-[var(--strix-text-muted)]">{model.version}</span>
                    </div>
                    <span className={cn(
                      "text-[9px] font-bold uppercase tracking-wider",
                      model.status === "active" ? "text-emerald-500" : "text-amber-500"
                    )}>
                      {model.status}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block">Accuracy</span>
                    <span className="text-lg font-bold text-[var(--strix-text)]">{model.accuracy}%</span>
                  </div>
                  <div className="text-right">
                    <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-wider block">F1</span>
                    <span className="text-lg font-bold text-[var(--strix-text)]">{model.f1}</span>
                  </div>
                  <button className={cn("text-[10px] font-semibold hover:underline", model.color)}>
                    View Details →
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Accuracy Gauge */}
        <div className="lg:col-span-4 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5 flex flex-col items-center justify-center">
          <span className="text-[9px] text-[var(--strix-text-muted)] uppercase tracking-widest mb-4">
            Composite Accuracy
          </span>
          <CircularProgress value={modelMetrics.accuracy} size={180} strokeWidth={12} />
          <div className="mt-4 text-center">
            <span className="text-[10px] text-[var(--strix-text-muted)]">
              Model 0.2 · STRIX Sentinel
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
              Confidence Trend (10-Day)
            </h3>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <div className="h-2 w-6 rounded-full bg-strix-primary dark:bg-strix-cyan" />
              <span className="text-[9px] text-[var(--strix-text-muted)]">Classifier</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-2 w-6 rounded-full bg-purple-500" />
              <span className="text-[9px] text-[var(--strix-text-muted)]">GNN</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-2 w-6 rounded-full bg-amber-500" />
              <span className="text-[9px] text-[var(--strix-text-muted)]">VAE</span>
            </div>
          </div>
        </div>

        {/* SVG Line Chart */}
        <div className="relative h-[200px] w-full">
          <svg className="w-full h-full" viewBox="0 0 600 200" preserveAspectRatio="none">
            {/* Grid lines */}
            {[0, 1, 2, 3, 4].map((i) => (
              <line
                key={`grid-${i}`}
                x1="0"
                y1={i * 50}
                x2="600"
                y2={i * 50}
                stroke="var(--strix-border)"
                strokeWidth="0.5"
                opacity="0.5"
              />
            ))}

            {/* Classifier line */}
            <polyline
              fill="none"
              stroke="#006B94"
              strokeWidth="2"
              className="dark:stroke-[#00F2FF]"
              points={modelConfidenceData.map((d, i) => `${i * 66.6},${200 - (d.classifier - 60) * 5}`).join(" ")}
            />
            {/* GNN line */}
            <polyline
              fill="none"
              stroke="#8B5CF6"
              strokeWidth="2"
              points={modelConfidenceData.map((d, i) => `${i * 66.6},${200 - (d.gnn - 60) * 5}`).join(" ")}
            />
            {/* VAE line */}
            <polyline
              fill="none"
              stroke="#F59E0B"
              strokeWidth="2"
              points={modelConfidenceData.map((d, i) => `${i * 66.6},${200 - (d.vae - 60) * 5}`).join(" ")}
            />
          </svg>
          {/* X-axis labels */}
          <div className="flex justify-between mt-2">
            {modelConfidenceData.map((d, i) => (
              <span key={i} className="text-[9px] text-[var(--strix-text-muted)] font-mono">{d.time}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Telemetry Stream */}
      <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Terminal className="h-4 w-4 text-[var(--strix-text-muted)]" />
          <h3 className="text-sm font-bold text-[var(--strix-text)]">
            Live Inference Stream
          </h3>
          <span className={cn(
            "ml-auto text-[9px] font-semibold uppercase tracking-wider flex items-center gap-1",
            liveFeed.status === "open" ? "text-emerald-500" : "text-amber-500"
          )}>
            <Activity className="h-3 w-3" />
            {liveFeed.status}
          </span>
        </div>

        <div className="bg-[#0D1117] dark:bg-[#080C14] rounded-xl border border-[#1E293B] overflow-hidden">
          <div className="flex items-center gap-1.5 px-4 py-2 border-b border-[#1E293B]">
            <div className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
            <div className="h-2.5 w-2.5 rounded-full bg-amber-500/70" />
            <div className="h-2.5 w-2.5 rounded-full bg-emerald-500/70" />
            <span className="text-[9px] text-gray-500 ml-2 font-mono">strix:sse:live-feed</span>
          </div>
          <div className="p-4 max-h-[280px] overflow-y-auto scrollbar-thin font-mono text-[11px] leading-6 space-y-0.5">
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
                      {" "}VAE {e.data.vaeMaliciousProb != null ? (e.data.vaeMaliciousProb * 100).toFixed(0) : "—"}%
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
