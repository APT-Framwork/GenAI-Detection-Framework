"use client"

import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { apiFetch } from "@/lib/api/client"
import { useLiveFeed } from "@/lib/api/live-feed"
import {
  AePanel,
  DqnPanel,
  GnnPanel,
  TransformerPanel,
  VaePanel,
} from "@/components/model-monitor/panels"
import { InferenceStream } from "@/components/model-monitor/inference-stream"
import { cn } from "@/lib/utils"
import { fakeLiveFeedActions } from "@/lib/demo-fake"
import { MODEL_REGISTRY, compositeMetrics, type ModelMetrics } from "@/lib/model-registry"
import {
  Brain,
  Gauge,
  Zap,
  BarChart3,
  Cpu,
} from "lucide-react"

interface ModelHealth {
  name: string
  version: string
  weightsSha256: string
  status: string
  driftKl?: number | null
}
interface ModelsResponse { models: ModelHealth[] }

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
  // Bump retained events so the panel can show real history (backfilled
  // from `/streams/live-feed/recent` on mount) and serve the Export buttons.
  const liveFeed = useLiveFeed({ maxEvents: 500, backfillLimit: 200 })
  const [expandedModel, setExpandedModel] = useState<string | null>(null)

  // The live-feed hook hands back { id, data } envelopes; the model
  // panels want the flat LiveFeedEvent array, freshest-first.
  // Demo-only: rewrite the displayed STRIX action (Exploitation → ESCALATE on
  // the latest event per host, Installation → ISOLATE_HOST). Cosmetic only;
  // feeds both the DQN panel and the inference stream. See lib/demo-fake.ts.
  const liveFeedEvents = useMemo(
    () => fakeLiveFeedActions(liveFeed.events.map((e) => e.data)),
    [liveFeed.events],
  )
  // "Pulse" the panel accent dots when a new event arrived within the
  // last few seconds — visual heartbeat that the SSE feed is live.
  const recentlyActive = useMemo(() => {
    const latest = liveFeedEvents[0]?.occurredAt
    if (!latest) return false
    const t = Date.parse(latest)
    return Number.isFinite(t) && Date.now() - t < 8_000
  }, [liveFeedEvents])

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

  // Per-model live status pill stays unchanged — we keep the active-models
  // section. The aggregate "engine health" badge that used `avgDriftKl`
  // was removed alongside the Avg Drift KPI.

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
            <span className="font-mono text-[10px]">RL_agent/evaluation/</span>. Live inference rate is
            sourced from the API and refreshes every 30 s.
          </p>
        </div>
      </div>

      {/* Top KPI Row — composite test-set metrics + live throughput. The
          Avg Drift KL tile was removed (the engine-health badge in the
          header depended on the same signal). */}
      <div data-tour="ai-kpis" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
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
      </div>

      {/* Live Inference — one panel per model. Every panel reads the
          same SSE event buffer and renders its model's outputs in its
          own colour-coded card. The accent dot pulses briefly when a
          fresh event arrives. */}
      <div data-tour="ai-live">
        <div className="flex items-center gap-2 mb-3">
          <Cpu className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
          <h2 className="text-sm font-bold text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk)]">
            Live Inference
          </h2>
          <span className="text-[10px] uppercase tracking-wider text-[var(--strix-text-muted)]">
            5 models · streaming via SSE
          </span>
          <span className="ml-auto flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[var(--strix-text-muted)]">
            <span className={cn(
              "w-1.5 h-1.5 rounded-full",
              liveFeed.status === "open" ? "bg-emerald-500 animate-pulse" : "bg-rose-500",
            )} />
            {liveFeed.status === "open" ? "connected" : liveFeed.status}
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4 items-start">
          <AePanel events={liveFeedEvents} active={recentlyActive} />
          <VaePanel events={liveFeedEvents} active={recentlyActive} />
          <GnnPanel events={liveFeedEvents} active={recentlyActive} />
          <TransformerPanel events={liveFeedEvents} active={recentlyActive} />
          <DqnPanel events={liveFeedEvents} active={recentlyActive} />
          <div className="md:col-span-2 xl:col-span-5 bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-2xl overflow-hidden">
            <div className="px-4 pt-3 pb-2 border-b border-[var(--strix-border)]/40">
              <h3 className="text-[13px] font-bold tracking-tight text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk)]">
                Inference Stream
              </h3>
              <p className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)]">
                latest 30 verdicts · all models
              </p>
            </div>
            <div className="max-h-[420px] overflow-y-auto">
              <InferenceStream events={liveFeedEvents} />
            </div>
          </div>
        </div>
      </div>

      {/* Active models — full width now that the composite gauge was removed. */}
      <div className="space-y-4">
        <div>
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
      </div>

    </div>
  )
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

