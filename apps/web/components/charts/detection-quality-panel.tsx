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
}

interface Quality {
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
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
  return { tp, fp, tn, fn, precision, recall, f1 };
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
      dst.push({ ts: now, score, gt: gtFromLabel(env.payload.label) });
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
      dst.push({ ts: now, score, gt: gtFromLabel(env.payload.label) });
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

      {/* Stacked bar */}
      <StackedBar buckets={buckets} />

      {/* Confusion matrix + cards */}
      <div className="grid grid-cols-2 gap-3 mt-3">
        <ConfusionMatrix q={quality} />
        <div className="grid grid-cols-3 gap-2">
          <Card label="P" value={quality.precision} />
          <Card label="R" value={quality.recall} />
          <Card label="F1" value={quality.f1} accent />
        </div>
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
