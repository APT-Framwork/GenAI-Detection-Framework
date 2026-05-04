// -----------------------------------------------------------------------------
// detection-quality-panel.tsx — AE vs VAE side-by-side detection quality
// (Phase 8).
//
// Subscribes to `ae` + `vae` ws frames (apps/web/lib/api/ws.ts). Each event is
// cached as `{ ts, score, gt }` in a 60 s rolling ring buffer (per model). The
// `gt` (ground truth) is derived from the backend-attached `label` field
// (tp/fn → malicious, fp/tn → benign, unknown → unknown).
//
// Score inversion: this lab's AE/VAE scores are inverted (benign → high,
// attack → low) — the backend works around it by sourcing the `label` from
// the GNN verdict, but the panel's threshold slider needs the score itself
// to point the right way, so `scoreFromAe` / `scoreFromVae` invert (1 - x).
//
// The threshold slider re-classifies the cached events client-side — no
// re-fetch — and recomputes:
//   * 60 s × 5 s-bucket stacked bar (TP/FP/TN/FN)
//   * 2×2 confusion matrix
//   * Precision / Recall / F1 cards
//
// Below: F1 comparison strip showing AE vs VAE F1 with a delta arrow.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import {
  useLogStream,
  type AePayload,
  type VaePayload,
  type Label,
} from "@/lib/api/ws";
import { severityColors } from "@/lib/design-tokens";

const WINDOW_MS = 60_000;
const BUCKET_MS = 5_000;
const BUCKETS = WINDOW_MS / BUCKET_MS; // 12
const PER_MODEL_CAP = 4_000;

type GroundTruth = "malicious" | "benign" | "unknown";

interface ScoredEvent {
  ts: number;
  score: number;
  gt: GroundTruth;
  tactics: string[];
  techniques: string[];
}

interface Quality {
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
  // Detection RATES — what the new panel surfaces in big % cards instead
  // of raw counts. tpr=recall (recovered for completeness); tnr is the
  // benign-respect rate; fpr is the alarm-fatigue indicator; fnr is the
  // miss rate.
  tpr: number;
  tnr: number;
  fpr: number;
  fnr: number;
}

interface BucketCounts {
  tp: number;
  fp: number;
  tn: number;
  fn: number;
}

const COLORS = {
  tp: "#22C55E", // green
  fn: "#EF4444", // red
  fp: "#F97316", // orange
  tn: "#94A3B8", // gray
} as const;

function gtFromLabel(label: Label | undefined): GroundTruth {
  if (label === "tp" || label === "fn") return "malicious";
  if (label === "fp" || label === "tn") return "benign";
  return "unknown";
}

// AE/VAE scores are INVERTED on this lab: benign auditd rule-80789 events
// produce anomaly_score / malicious_prob ≈ 1.0, while STRIX-tagged attack
// events (rule 100xxx) score ≈ 0.15. The streams.py backend works around
// this by labelling AE/VAE frames from the GNN's verdict rather than their
// own scores (see apps/api/src/strix_api/api/routes/streams.py `_attach_label`
// docstring). For the detection-quality panel to compute meaningful TP/FP
// against its own slider threshold, we invert the score here so that "score
// >= threshold ⇒ predicted malicious" actually holds.
function scoreFromAe(p: AePayload): number | null {
  if (typeof p.anomaly_score === "number") return 1 - p.anomaly_score;
  if (typeof p.recon_error === "number") {
    return 1 / (1 + p.recon_error);
  }
  return null;
}

function scoreFromVae(p: VaePayload): number | null {
  if (typeof p.malicious_prob === "number") return 1 - p.malicious_prob;
  return null;
}

function classify(events: ReadonlyArray<ScoredEvent>, threshold: number): Quality {
  let tp = 0;
  let fp = 0;
  let tn = 0;
  let fn = 0;
  for (const e of events) {
    if (e.gt === "unknown") continue;
    const predPos = e.score >= threshold;
    const actualPos = e.gt === "malicious";
    if (predPos && actualPos) tp += 1;
    else if (predPos && !actualPos) fp += 1;
    else if (!predPos && actualPos) fn += 1;
    else tn += 1;
  }
  const precision = tp + fp > 0 ? tp / (tp + fp) : 0;
  const recall = tp + fn > 0 ? tp / (tp + fn) : 0;
  const f1 = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;
  // Rate denominators are the ground-truth class counts, not the predicted
  // class counts (precision/recall already cover those).
  const tpr = tp + fn > 0 ? tp / (tp + fn) : 0;            // = recall
  const tnr = tn + fp > 0 ? tn / (tn + fp) : 0;            // = specificity
  const fpr = tn + fp > 0 ? fp / (tn + fp) : 0;            // = 1 - tnr
  const fnr = tp + fn > 0 ? fn / (tp + fn) : 0;            // = 1 - tpr
  return { tp, fp, tn, fn, precision, recall, f1, tpr, tnr, fpr, fnr };
}

interface TacticBreakdown {
  // Per-tactic aggregate of labelled events (gt ≠ unknown).
  tactic: string;
  total: number;       // count of events tagged with this tactic in window
  detected: number;    // of those, count where predPos & gt malicious (TP)
  missed: number;      // of those, count where !predPos & gt malicious (FN)
  rate: number;        // detected / (detected + missed) — per-tactic recall
}

function tacticBreakdown(
  events: ReadonlyArray<ScoredEvent>,
  threshold: number,
): TacticBreakdown[] {
  // tactic -> {detected, missed, total}
  const acc: Record<string, { detected: number; missed: number; total: number }> = {};
  for (const e of events) {
    if (!e.tactics || e.tactics.length === 0) continue;
    const predPos = e.score >= threshold;
    const actualPos = e.gt === "malicious";
    for (const t of e.tactics) {
      const slot = (acc[t] ||= { detected: 0, missed: 0, total: 0 });
      slot.total += 1;
      if (actualPos && predPos) slot.detected += 1;
      else if (actualPos && !predPos) slot.missed += 1;
    }
  }
  const out: TacticBreakdown[] = Object.entries(acc).map(([tactic, v]) => {
    const denom = v.detected + v.missed;
    return {
      tactic,
      total: v.total,
      detected: v.detected,
      missed: v.missed,
      rate: denom > 0 ? v.detected / denom : 0,
    };
  });
  // Most-impacted first.
  out.sort((a, b) => b.total - a.total);
  return out;
}

function bucketize(
  events: ReadonlyArray<ScoredEvent>,
  threshold: number,
  now: number,
): BucketCounts[] {
  const out: BucketCounts[] = Array.from({ length: BUCKETS }, () => ({
    tp: 0,
    fp: 0,
    tn: 0,
    fn: 0,
  }));
  const start = now - WINDOW_MS;
  for (const e of events) {
    if (e.gt === "unknown") continue;
    if (e.ts < start || e.ts > now) continue;
    const idx = Math.min(BUCKETS - 1, Math.floor((e.ts - start) / BUCKET_MS));
    const predPos = e.score >= threshold;
    const actualPos = e.gt === "malicious";
    const bucket = out[idx];
    if (predPos && actualPos) bucket.tp += 1;
    else if (predPos && !actualPos) bucket.fp += 1;
    else if (!predPos && actualPos) bucket.fn += 1;
    else bucket.tn += 1;
  }
  return out;
}

interface DetectionQualityPanelProps {
  className?: string;
}

export function DetectionQualityPanel({ className }: DetectionQualityPanelProps) {
  const stream = useLogStream(["ae", "vae"]);
  const aeSeq = stream.seq.ae;
  const vaeSeq = stream.seq.vae;

  const aeRef = useRef<ScoredEvent[]>([]);
  const vaeRef = useRef<ScoredEvent[]>([]);
  const aeLastSeq = useRef(0);
  const vaeLastSeq = useRef(0);
  const [, setTick] = useState(0);

  // Defaults match the model-card recommendations:
  //   * AE  = 0.5  (balanced split on calibrated [0,1] anomaly_score; the
  //                 Youden-J threshold from training doesn't transfer because
  //                 the loader's score formula differs from the notebook's
  //                 — see docs/MODELS_REFERENCE.md §11).
  //   * VAE = 0.7  (matches INFECTION_VAE_PROB_THRESHOLD used in production
  //                 chain-decision logic; aligns with the calibrator's
  //                 documented operating point).
  const [aeThreshold, setAeThreshold] = useState(0.5);
  const [vaeThreshold, setVaeThreshold] = useState(0.7);

  // Drain new AE frames into the ring buffer.
  useEffect(() => {
    if (aeSeq <= aeLastSeq.current) return;
    const buf = stream.frames.ae;
    const fresh = buf.slice(buf.length - (aeSeq - aeLastSeq.current));
    aeLastSeq.current = aeSeq;
    const dst = aeRef.current;
    const now = Date.now();
    for (const env of fresh) {
      const score = scoreFromAe(env.payload);
      if (score == null) continue;
      dst.push({
        ts: now,
        score,
        gt: gtFromLabel(env.payload.label),
        tactics: pickStringArray(env.payload, "mitre_tactics"),
        techniques: pickStringArray(env.payload, "mitre_techniques"),
      });
    }
    pruneWindow(dst, now);
    if (dst.length > PER_MODEL_CAP) dst.splice(0, dst.length - PER_MODEL_CAP);
    setTick((n) => n + 1);
  }, [aeSeq, stream.frames.ae]);

  useEffect(() => {
    if (vaeSeq <= vaeLastSeq.current) return;
    const buf = stream.frames.vae;
    const fresh = buf.slice(buf.length - (vaeSeq - vaeLastSeq.current));
    vaeLastSeq.current = vaeSeq;
    const dst = vaeRef.current;
    const now = Date.now();
    for (const env of fresh) {
      const score = scoreFromVae(env.payload);
      if (score == null) continue;
      dst.push({
        ts: now,
        score,
        gt: gtFromLabel(env.payload.label),
        tactics: pickStringArray(env.payload, "mitre_tactics"),
        techniques: pickStringArray(env.payload, "mitre_techniques"),
      });
    }
    pruneWindow(dst, now);
    if (dst.length > PER_MODEL_CAP) dst.splice(0, dst.length - PER_MODEL_CAP);
    setTick((n) => n + 1);
  }, [vaeSeq, stream.frames.vae]);

  // 1 Hz tick to expire the rolling window when frames slow down.
  useEffect(() => {
    const t = setInterval(() => {
      const now = Date.now();
      pruneWindow(aeRef.current, now);
      pruneWindow(vaeRef.current, now);
      setTick((n) => n + 1);
    }, 1000);
    return () => clearInterval(t);
  }, []);

  const now = Date.now();

  const aeQuality = useMemo(
    () => classify(aeRef.current, aeThreshold),
    // re-derive on tick + threshold
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [aeSeq, aeThreshold],
  );
  const vaeQuality = useMemo(
    () => classify(vaeRef.current, vaeThreshold),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [vaeSeq, vaeThreshold],
  );

  const aeBuckets = useMemo(
    () => bucketize(aeRef.current, aeThreshold, now),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [aeSeq, aeThreshold],
  );
  const vaeBuckets = useMemo(
    () => bucketize(vaeRef.current, vaeThreshold, now),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [vaeSeq, vaeThreshold],
  );

  // Per-model tactic breakdown — used by the shared tactic-distribution
  // section below the two sub-panels.
  const aeTactics = useMemo(
    () => tacticBreakdown(aeRef.current, aeThreshold),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [aeSeq, aeThreshold],
  );
  const vaeTactics = useMemo(
    () => tacticBreakdown(vaeRef.current, vaeThreshold),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [vaeSeq, vaeThreshold],
  );

  const f1Delta = vaeQuality.f1 - aeQuality.f1;

  return (
    <div className={cn("w-full", className)}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
          Detection Quality — AE vs VAE
        </h3>
        <span className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          rolling 60s · 5s buckets
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ModelSubPanel
          name="AE"
          quality={aeQuality}
          buckets={aeBuckets}
          threshold={aeThreshold}
          onThresholdChange={setAeThreshold}
          totalCached={aeRef.current.length}
        />
        <ModelSubPanel
          name="VAE"
          quality={vaeQuality}
          buckets={vaeBuckets}
          threshold={vaeThreshold}
          onThresholdChange={setVaeThreshold}
          totalCached={vaeRef.current.length}
        />
      </div>

      {/* MITRE tactic distribution — pie + per-tactic recall, side-by-side AE/VAE */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <TacticSection title="AE — Tactic distribution" rows={aeTactics} />
        <TacticSection title="VAE — Tactic distribution" rows={vaeTactics} />
      </div>

      {/* F1 comparison strip */}
      <div className="mt-4 rounded-xl border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] p-3 flex items-center gap-4">
        <span className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          F1 comparison
        </span>
        <F1Bar label="AE" value={aeQuality.f1} color="#0EA5E9" />
        <F1Bar label="VAE" value={vaeQuality.f1} color="#8A2BE2" />
        <div className="ml-auto flex items-center gap-1.5 text-[12px] font-mono">
          <span
            style={{
              color:
                f1Delta > 0.001
                  ? severityColors.low.fg
                  : f1Delta < -0.001
                    ? severityColors.high.fg
                    : "#94A3B8",
            }}
          >
            {f1Delta > 0.001 ? "▲" : f1Delta < -0.001 ? "▼" : "≈"}
          </span>
          <span className="text-[#00343d] dark:text-[var(--strix-text)] font-bold">
            {Math.abs(f1Delta).toFixed(3)}
          </span>
          <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)] text-[10px]">
            {f1Delta >= 0 ? "VAE > AE" : "AE > VAE"}
          </span>
        </div>
      </div>
    </div>
  );
}

function ModelSubPanel({
  name,
  quality,
  buckets,
  threshold,
  onThresholdChange,
  totalCached,
}: {
  name: string;
  quality: Quality;
  buckets: BucketCounts[];
  threshold: number;
  onThresholdChange: (v: number) => void;
  totalCached: number;
}) {
  const total = quality.tp + quality.fp + quality.tn + quality.fn;
  return (
    <div className="rounded-xl border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] bg-[var(--strix-bg-card)] dark:bg-[var(--strix-bg-surface)] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-bold font-mono text-[#00343d] dark:text-[var(--strix-text)]">
            {name}
          </span>
          <span className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            {totalCached} cached · {total} labelled
          </span>
        </div>
      </div>

      {/* Stacked bar — keeps the time-series story */}
      <StackedBar buckets={buckets} />

      {/* Donut (TP/FP/TN/FN ratio) + Rate cards (TPR/TNR/FPR/FNR) */}
      <div className="grid grid-cols-[auto_1fr] gap-3 mt-3 items-center">
        <Donut q={quality} />
        <RateGrid q={quality} />
      </div>

      {/* Per-class precision/recall/F1 — kept compact */}
      <div className="grid grid-cols-3 gap-2 mt-3">
        <Card label="P" value={quality.precision} />
        <Card label="R" value={quality.recall} />
        <Card label="F1" value={quality.f1} accent />
      </div>

      {/* Threshold slider */}
      <div className="mt-3">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-1">
          <span>threshold</span>
          <span className="font-mono text-[#00343d] dark:text-[var(--strix-text)]">
            {threshold.toFixed(2)}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={threshold}
          onChange={(e) => onThresholdChange(parseFloat(e.target.value))}
          className="w-full accent-[#00666d] dark:accent-strix-cyan"
        />
      </div>
    </div>
  );
}

function StackedBar({ buckets }: { buckets: BucketCounts[] }) {
  const W = 280;
  const H = 64;
  const slot = W / buckets.length;
  const max = Math.max(
    1,
    ...buckets.map((b) => b.tp + b.fp + b.tn + b.fn),
  );
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-16" preserveAspectRatio="none">
      {buckets.map((b, i) => {
        const total = b.tp + b.fp + b.tn + b.fn;
        if (total === 0) return null;
        const x = i * slot + 1;
        const w = slot - 2;
        const order: Array<keyof BucketCounts> = ["tn", "fp", "fn", "tp"];
        let y = H;
        return (
          <g key={i}>
            {order.map((k) => {
              const v = b[k];
              if (v === 0) return null;
              const h = (v / max) * H;
              y -= h;
              return (
                <rect
                  key={k}
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  fill={COLORS[k]}
                  opacity={0.85}
                />
              );
            })}
          </g>
        );
      })}
      {/* baseline */}
      <line x1={0} y1={H - 0.5} x2={W} y2={H - 0.5} stroke="rgba(128,182,195,0.3)" />
    </svg>
  );
}

function ConfusionMatrix({ q }: { q: Quality }) {
  return (
    <div className="grid grid-cols-2 gap-1 text-center text-[10px] font-mono">
      <Cell label="TP" value={q.tp} color={COLORS.tp} />
      <Cell label="FP" value={q.fp} color={COLORS.fp} />
      <Cell label="FN" value={q.fn} color={COLORS.fn} />
      <Cell label="TN" value={q.tn} color={COLORS.tn} />
    </div>
  );
}

function Cell({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div
      className="rounded-md border py-1.5"
      style={{ borderColor: `${color}55`, background: `${color}14` }}
    >
      <div className="text-[9px] uppercase tracking-wider" style={{ color }}>
        {label}
      </div>
      <div className="text-[14px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
        {value}
      </div>
    </div>
  );
}

function Card({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: number;
  accent?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-md border py-1.5 px-2 text-center",
        accent
          ? "border-[#00666d]/40 bg-[#00666d]/10 dark:border-strix-cyan/40 dark:bg-strix-cyan/10"
          : "border-[rgba(128,182,195,0.25)]",
      )}
    >
      <div className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        {label}
      </div>
      <div className="text-[12px] font-bold font-mono text-[#00343d] dark:text-[var(--strix-text)]">
        {value.toFixed(3)}
      </div>
    </div>
  );
}

function F1Bar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="flex items-center gap-2 flex-1 min-w-0">
      <span className="text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)] w-8">
        {label}
      </span>
      <div className="relative flex-1 h-1.5 rounded-full bg-[rgba(128,182,195,0.2)] overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${pct}%`,
            background: color,
            transition: "width 300ms ease",
          }}
        />
      </div>
      <span className="text-[10px] font-mono text-[#00343d] dark:text-[var(--strix-text)] w-12 text-right">
        {value.toFixed(3)}
      </span>
    </div>
  );
}

function pruneWindow(arr: ScoredEvent[], now: number): void {
  const cutoff = now - WINDOW_MS;
  let i = 0;
  while (i < arr.length && arr[i].ts < cutoff) i += 1;
  if (i > 0) arr.splice(0, i);
}

function pickStringArray(p: Record<string, unknown>, key: string): string[] {
  const v = p[key];
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === "string");
}

// SVG donut: renders a stacked-segment donut for TP/FP/TN/FN. Used in
// place of the old 2×2 ConfusionMatrix grid — shows ratios at a glance.
function Donut({ q, size = 96 }: { q: Quality; size?: number }) {
  const total = q.tp + q.fp + q.tn + q.fn;
  const r = size / 2 - 8;
  const cx = size / 2;
  const cy = size / 2;
  const C = 2 * Math.PI * r;
  // Segment order (clockwise): tp → fp → fn → tn — green/orange/red/gray.
  const order: Array<keyof BucketCounts> = ["tp", "fp", "fn", "tn"];
  let cursor = 0;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* track */}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="rgba(128,182,195,0.18)"
          strokeWidth={10}
        />
        {total > 0 && order.map((k) => {
          const v = q[k];
          if (v === 0) return null;
          const frac = v / total;
          const len = frac * C;
          const seg = (
            <circle
              key={k}
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke={COLORS[k]}
              strokeWidth={10}
              strokeDasharray={`${len} ${C}`}
              strokeDashoffset={-cursor}
              transform={`rotate(-90 ${cx} ${cy})`}
            />
          );
          cursor += len;
          return seg;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[18px] font-bold font-mono text-[#00343d] dark:text-[var(--strix-text)] leading-none">
          {total}
        </span>
        <span className="text-[8px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5">
          labelled
        </span>
      </div>
    </div>
  );
}

function RateGrid({ q }: { q: Quality }) {
  // Each rate gets a colour cue: TPR + TNR are "good" (green), FPR + FNR
  // are "cost" (orange/red). The bar fill width visualises magnitude;
  // the percent in the corner is the precise value.
  const items: Array<{ label: string; long: string; pct: number; color: string; good: boolean }> = [
    { label: "TPR", long: "attacks caught", pct: q.tpr, color: COLORS.tp, good: true },
    { label: "TNR", long: "benign respected", pct: q.tnr, color: "#0EA5E9", good: true },
    { label: "FPR", long: "false alarms", pct: q.fpr, color: COLORS.fp, good: false },
    { label: "FNR", long: "attacks missed", pct: q.fnr, color: COLORS.fn, good: false },
  ];
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {items.map((it) => {
        const pct = Math.round(Math.max(0, Math.min(1, it.pct)) * 100);
        return (
          <div
            key={it.label}
            className="rounded-md border px-2 py-1.5"
            style={{ borderColor: `${it.color}55`, background: `${it.color}10` }}
          >
            <div className="flex items-baseline justify-between">
              <span
                className="text-[9px] font-bold uppercase tracking-wider"
                style={{ color: it.color }}
              >
                {it.label}
              </span>
              <span className="text-[12px] font-bold font-mono text-[#00343d] dark:text-[var(--strix-text)]">
                {pct}%
              </span>
            </div>
            <div className="text-[8px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mb-1 truncate">
              {it.long}
            </div>
            <div className="relative h-1 rounded-full bg-[rgba(128,182,195,0.2)] overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 rounded-full"
                style={{
                  width: `${pct}%`,
                  background: it.color,
                  transition: "width 300ms ease",
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Pie chart: renders top-N tactics by *labelled-event count* (denominator
// = events with that tactic AND ground-truth ≠ unknown). Slices coloured
// by an HSL hash of the tactic ID so adjacent ones stay distinguishable.
const TACTIC_PIE_COLORS = [
  "#0EA5E9", "#22C55E", "#F97316", "#A855F7", "#EAB308",
  "#EF4444", "#14B8A6", "#8B5CF6", "#06B6D4", "#84CC16",
] as const;

function TacticPie({ rows, size = 140 }: { rows: TacticBreakdown[]; size?: number }) {
  const top = rows.slice(0, 8);
  const grandTotal = top.reduce((s, r) => s + r.total, 0);
  const r = size / 2 - 4;
  const cx = size / 2;
  const cy = size / 2;
  if (grandTotal === 0) {
    return (
      <div
        className="flex items-center justify-center text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)]"
        style={{ width: size, height: size }}
      >
        no MITRE-tagged
        <br />
        events yet
      </div>
    );
  }
  let cursor = -Math.PI / 2; // 12 o'clock
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {top.map((row, i) => {
        const frac = row.total / grandTotal;
        const start = cursor;
        const end = cursor + frac * 2 * Math.PI;
        cursor = end;
        const x1 = cx + r * Math.cos(start);
        const y1 = cy + r * Math.sin(start);
        const x2 = cx + r * Math.cos(end);
        const y2 = cy + r * Math.sin(end);
        const largeArc = end - start > Math.PI ? 1 : 0;
        const d = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`;
        return (
          <path
            key={row.tactic}
            d={d}
            fill={TACTIC_PIE_COLORS[i % TACTIC_PIE_COLORS.length]}
            opacity={0.85}
            stroke="rgba(255,255,255,0.4)"
            strokeWidth={0.5}
          />
        );
      })}
    </svg>
  );
}

function TacticSection({
  title,
  rows,
}: {
  title: string;
  rows: TacticBreakdown[];
}) {
  return (
    <div className="rounded-xl border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] bg-[var(--strix-bg-card)] dark:bg-[var(--strix-bg-surface)] p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-bold uppercase tracking-wider text-[#00343d] dark:text-[var(--strix-text)]">
          {title}
        </span>
        <span className="text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {rows.length} tactic{rows.length === 1 ? "" : "s"} · top 8
        </span>
      </div>
      <div className="grid grid-cols-[auto_1fr] gap-3 items-center">
        <TacticPie rows={rows} />
        <TacticTable rows={rows} />
      </div>
    </div>
  );
}

function TacticTable({ rows }: { rows: TacticBreakdown[] }) {
  const top = rows.slice(0, 8);
  if (top.length === 0) {
    return (
      <div className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] py-2">
        Waiting for MITRE-tagged events…
      </div>
    );
  }
  return (
    <div className="space-y-1">
      {top.map((row, i) => {
        const pct = Math.round(row.rate * 100);
        const color = TACTIC_PIE_COLORS[i % TACTIC_PIE_COLORS.length];
        return (
          <div key={row.tactic} className="flex items-center gap-2 text-[10px]">
            <span
              className="inline-block w-2 h-2 rounded-full shrink-0"
              style={{ background: color }}
            />
            <span className="font-mono text-[#00343d] dark:text-[var(--strix-text)] flex-1 truncate">
              {row.tactic}
            </span>
            <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)] tabular-nums w-10 text-right">
              {row.total}
            </span>
            <div className="relative w-16 h-1 rounded-full bg-[rgba(128,182,195,0.2)] overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 rounded-full"
                style={{ width: `${pct}%`, background: color }}
              />
            </div>
            <span className="font-mono tabular-nums text-[#00343d] dark:text-[var(--strix-text)] w-8 text-right">
              {pct}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
