// -----------------------------------------------------------------------------
// detection-volume-panel.tsx — Kibana-style stacked bar chart of TN/FP volume
// over a rolling 10-minute window. Replaces the older AE-vs-VAE comparison
// panel: this surface answers the operational question "are we drowning in
// false alarms?" rather than the engineering question "which model has higher
// F1?".
//
// Subscribes to AE + VAE WS frames via `useLogStream`. Each frame carries a
// `label` field (`tp|fp|tn|fn|unknown`) populated by the backend in
// `streams.py:_attach_label` from the GNN ground-truth verdict — so this
// component never needs to interpret raw scores.
//
// Only the negative-class outcomes (TN + FP) are stacked into bars. TP / FN
// counts are surfaced as side pills so the bar metaphor stays honest: one
// model, one outcome family per bar.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Activity } from "lucide-react";
import { useLogStream, type Label } from "@/lib/api/ws";

const WINDOW_MS = 600_000; // 10 min
const BUCKET_MS = 30_000;  // 30 s
const NUM_BUCKETS = WINDOW_MS / BUCKET_MS; // 20

const COLOR_TN = "#7C8FA1";   // slate halfway between 500/400 — readable in both themes
const COLOR_FP = "#F59E0B";   // amber-500 — alarm noise

type ModelToggle = "ae" | "vae" | "both";

interface Bucket {
  start: number;       // ms epoch (bucket left edge)
  tn: number;
  fp: number;
}

export function DetectionVolumePanel({ className }: { className?: string }) {
  const { frames } = useLogStream(["ae", "vae"]);
  const [model, setModel] = useState<ModelToggle>("both");
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // Slide the window — re-derive buckets every 5 s so the rightmost bucket
  // tracks "now" even when no new frames arrive. 5 s is well below the
  // 30 s bucket size, so visual lag is bounded.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(id);
  }, []);

  // Derive aligned buckets + side counters from the AE/VAE buffers.
  const { buckets, sideCounts, totals } = useMemo(() => {
    const cutoff = now - WINDOW_MS;
    const windowStart = Math.floor(cutoff / BUCKET_MS) * BUCKET_MS;

    const arr: Bucket[] = Array.from({ length: NUM_BUCKETS }, (_, i) => ({
      start: windowStart + i * BUCKET_MS,
      tn: 0,
      fp: 0,
    }));
    const idxByStart = new Map(arr.map((b, i) => [b.start, i]));

    let tp = 0;
    let fn = 0;
    let totalTn = 0;
    let totalFp = 0;

    const consider = (ts: string, label: Label | undefined) => {
      if (!label || label === "unknown") return;
      const t = Date.parse(ts);
      if (!Number.isFinite(t) || t < cutoff || t > now + BUCKET_MS) return;
      if (label === "tp") { tp++; return; }
      if (label === "fn") { fn++; return; }
      const start = Math.floor(t / BUCKET_MS) * BUCKET_MS;
      const i = idxByStart.get(start);
      if (i == null) return;
      if (label === "tn") { arr[i].tn++; totalTn++; }
      else if (label === "fp") { arr[i].fp++; totalFp++; }
    };

    if (model === "ae" || model === "both") {
      for (const f of frames.ae) consider(f.ts, f.payload.label);
    }
    if (model === "vae" || model === "both") {
      for (const f of frames.vae) consider(f.ts, f.payload.label);
    }

    return {
      buckets: arr,
      sideCounts: { tp, fn },
      totals: { tn: totalTn, fp: totalFp },
    };
  }, [frames.ae, frames.vae, model, now]);

  // Y-scale: max stack height across all buckets (≥ 1 to avoid div-by-zero).
  const yMax = useMemo(() => {
    let m = 0;
    for (const b of buckets) m = Math.max(m, b.tn + b.fp);
    return Math.max(1, m);
  }, [buckets]);

  const isEmpty = totals.tn === 0 && totals.fp === 0 && sideCounts.tp === 0 && sideCounts.fn === 0;

  return (
    <div className={`text-[var(--strix-text)] ${className ?? ""}`}>
      <Header
        model={model}
        onModel={setModel}
        totals={totals}
        sideCounts={sideCounts}
      />

      {isEmpty ? (
        <EmptyState />
      ) : (
        <Chart
          buckets={buckets}
          yMax={yMax}
          hoverIdx={hoverIdx}
          onHover={setHoverIdx}
        />
      )}

      <Legend />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Header — title, caption, model toggle, counter pills
// ────────────────────────────────────────────────────────────────────────────

function Header({
  model,
  onModel,
  totals,
  sideCounts,
}: {
  model: ModelToggle;
  onModel: (m: ModelToggle) => void;
  totals: { tn: number; fp: number };
  sideCounts: { tp: number; fn: number };
}) {
  const fpRate = totals.tn + totals.fp === 0
    ? 0
    : (totals.fp / (totals.tn + totals.fp)) * 100;

  return (
    <div className="flex items-start justify-between gap-3 mb-4">
      <div>
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-[var(--strix-text-muted)]" />
          <h3 className="text-[14px] font-bold text-[var(--strix-text)]">
            Detection Volume
          </h3>
        </div>
        <p className="text-[10px] text-[var(--strix-text-muted)] mt-0.5">
          10 min · 30 s buckets · TN / FP · live AE+VAE feed
        </p>
      </div>

      <div className="flex items-center gap-2">
        <CounterPill label="TN" value={totals.tn} color={COLOR_TN} />
        <CounterPill label="FP" value={totals.fp} color={COLOR_FP} />
        <span className="text-[10px] text-[var(--strix-text-muted)] tabular-nums">
          fp rate {fpRate.toFixed(1)}%
        </span>
        <span className="mx-1.5 h-4 w-px bg-[var(--strix-border)]" />
        <span className="text-[10px] text-[var(--strix-text-muted)] tabular-nums">
          tp {sideCounts.tp} · fn {sideCounts.fn}
        </span>
        <span className="mx-1.5 h-4 w-px bg-[var(--strix-border)]" />
        <ModelToggleButtons value={model} onChange={onModel} />
      </div>
    </div>
  );
}

function CounterPill({ label, value, color }: { label: string; value: number; color: string }) {
  // Pulse on increment using a ref to track previous value.
  const prev = useRef(value);
  const [pulse, setPulse] = useState(false);
  useEffect(() => {
    if (value > prev.current) {
      setPulse(true);
      const id = setTimeout(() => setPulse(false), 240);
      prev.current = value;
      return () => clearTimeout(id);
    }
    prev.current = value;
  }, [value]);

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold tabular-nums transition-transform ${pulse ? "scale-110" : ""}`}
      style={{ backgroundColor: `${color}22`, color, border: `1px solid ${color}55` }}
    >
      <span className="opacity-70">{label}</span>
      <span>{value}</span>
    </span>
  );
}

function ModelToggleButtons({ value, onChange }: { value: ModelToggle; onChange: (m: ModelToggle) => void }) {
  const opts: ModelToggle[] = ["ae", "vae", "both"];
  return (
    <div className="inline-flex rounded-md border border-[var(--strix-border)] overflow-hidden">
      {opts.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={`px-2 py-0.5 text-[10px] uppercase font-semibold tracking-wider transition-colors ${
            value === opt
              ? "bg-[var(--strix-bg-surface)] text-[var(--strix-text)]"
              : "bg-transparent text-[var(--strix-text-muted)] hover:text-[var(--strix-text)]"
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Chart — Kibana stacked vertical bars with hover guide rail
// ────────────────────────────────────────────────────────────────────────────

const CHART_HEIGHT = 220;
const CHART_VBOX_W = 1000;
const CHART_PAD_TOP = 8;
const CHART_PAD_BOTTOM = 22; // x-axis labels
const CHART_PAD_LEFT = 32;   // y-axis labels
const CHART_PAD_RIGHT = 8;
const PLOT_W = CHART_VBOX_W - CHART_PAD_LEFT - CHART_PAD_RIGHT;
const PLOT_H = CHART_HEIGHT - CHART_PAD_TOP - CHART_PAD_BOTTOM;

function Chart({
  buckets,
  yMax,
  hoverIdx,
  onHover,
}: {
  buckets: Bucket[];
  yMax: number;
  hoverIdx: number | null;
  onHover: (i: number | null) => void;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const slotW = PLOT_W / NUM_BUCKETS;
  const barW = Math.max(4, Math.floor(slotW * 0.68));
  const barOffset = (slotW - barW) / 2;

  // Y ticks at 0/25/50/75/100 % of yMax.
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(yMax * f));

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = wrapRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const xInPlot = (x / rect.width) * CHART_VBOX_W - CHART_PAD_LEFT;
    if (xInPlot < 0 || xInPlot > PLOT_W) {
      onHover(null);
      return;
    }
    const i = Math.min(NUM_BUCKETS - 1, Math.max(0, Math.floor(xInPlot / slotW)));
    onHover(i);
  };

  return (
    <div
      ref={wrapRef}
      className="relative"
      onMouseMove={onMove}
      onMouseLeave={() => onHover(null)}
    >
      <svg
        viewBox={`0 0 ${CHART_VBOX_W} ${CHART_HEIGHT}`}
        preserveAspectRatio="none"
        className="w-full h-[220px]"
      >
        {/* Y-axis grid + labels */}
        {yTicks.map((tickVal, i) => {
          const f = i / (yTicks.length - 1);
          const y = CHART_PAD_TOP + (1 - f) * PLOT_H;
          return (
            <g key={i}>
              <line
                x1={CHART_PAD_LEFT}
                x2={CHART_VBOX_W - CHART_PAD_RIGHT}
                y1={y}
                y2={y}
                stroke="var(--strix-border)"
                strokeWidth={0.5}
                strokeDasharray={i === 0 ? "0" : "2,3"}
                opacity={i === 0 ? 0.6 : 0.4}
              />
              <text
                x={CHART_PAD_LEFT - 4}
                y={y + 3}
                textAnchor="end"
                fontSize={9}
                className="fill-[var(--strix-text-muted)]"
              >
                {tickVal}
              </text>
            </g>
          );
        })}

        {/* Bars */}
        {buckets.map((b, i) => {
          const total = b.tn + b.fp;
          if (total === 0) return null;
          const x = CHART_PAD_LEFT + i * slotW + barOffset;
          const tnH = (b.tn / yMax) * PLOT_H;
          const fpH = (b.fp / yMax) * PLOT_H;
          const yTn = CHART_PAD_TOP + PLOT_H - tnH;
          const yFp = yTn - fpH;
          const isHover = hoverIdx === i;

          return (
            <g key={i} opacity={hoverIdx == null || isHover ? 1 : 0.55}>
              {b.tn > 0 && (
                <rect
                  x={x}
                  y={yTn}
                  width={barW}
                  height={Math.max(1, tnH)}
                  fill={COLOR_TN}
                />
              )}
              {b.fp > 0 && (
                <rect
                  x={x}
                  y={yFp}
                  width={barW}
                  height={Math.max(1, fpH)}
                  fill={COLOR_FP}
                />
              )}
            </g>
          );
        })}

        {/* X-axis labels — every 4 buckets = every 2 minutes. */}
        {buckets.map((b, i) => {
          if (i % 4 !== 0 && i !== buckets.length - 1) return null;
          const x = CHART_PAD_LEFT + i * slotW + slotW / 2;
          return (
            <text
              key={`x-${i}`}
              x={x}
              y={CHART_HEIGHT - 6}
              textAnchor="middle"
              fontSize={9}
              className="fill-[var(--strix-text-muted)]"
            >
              {fmtTime(b.start)}
            </text>
          );
        })}

        {/* Hover guide rail */}
        {hoverIdx != null && (
          <line
            x1={CHART_PAD_LEFT + hoverIdx * slotW + slotW / 2}
            x2={CHART_PAD_LEFT + hoverIdx * slotW + slotW / 2}
            y1={CHART_PAD_TOP}
            y2={CHART_PAD_TOP + PLOT_H}
            stroke="var(--strix-text-muted)"
            strokeWidth={0.7}
            strokeDasharray="2,3"
            opacity={0.55}
          />
        )}
      </svg>

      {hoverIdx != null && <Tooltip bucket={buckets[hoverIdx]} />}
    </div>
  );
}

function Tooltip({ bucket }: { bucket: Bucket }) {
  const total = bucket.tn + bucket.fp;
  const fpRate = total === 0 ? 0 : (bucket.fp / total) * 100;
  const start = new Date(bucket.start);
  const end = new Date(bucket.start + BUCKET_MS);

  return (
    <div className="absolute top-2 right-2 px-3 py-2 rounded-md bg-[var(--strix-bg-card)] border border-[var(--strix-border)] shadow-md pointer-events-none text-[10px] tabular-nums min-w-[180px]">
      <div className="font-mono text-[var(--strix-text-muted)] mb-1">
        {fmtTime(start.getTime())} – {fmtTime(end.getTime())}
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-[var(--strix-text)]">TN</span>
        <span className="font-bold" style={{ color: COLOR_TN }}>{bucket.tn}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-[var(--strix-text)]">FP</span>
        <span className="font-bold" style={{ color: COLOR_FP }}>{bucket.fp}</span>
      </div>
      <div className="mt-1 pt-1 border-t border-[var(--strix-border)] flex items-center justify-between gap-3">
        <span className="text-[var(--strix-text-muted)]">fp rate</span>
        <span className="font-bold text-[var(--strix-text)]">{fpRate.toFixed(1)}%</span>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Empty state + legend
// ────────────────────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div
      className="h-[220px] rounded-md flex items-center justify-center"
      style={{
        backgroundImage:
          "repeating-linear-gradient(45deg, transparent, transparent 6px, rgba(135,237,246,0.08) 6px, rgba(135,237,246,0.08) 7px)",
        border: "1px dashed rgba(135,237,246,0.35)",
      }}
    >
      <p className="text-[11px] text-[var(--strix-text-muted)] italic">
        awaiting AE/VAE frames…
      </p>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex items-center gap-4 mt-3 text-[10px] text-[var(--strix-text-muted)]">
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-4 rounded-sm" style={{ background: COLOR_TN }} />
        <span>TN — true negatives (correctly ignored)</span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-4 rounded-sm" style={{ background: COLOR_FP }} />
        <span>FP — false positives (alarm noise)</span>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────

function fmtTime(ms: number): string {
  const d = new Date(ms);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}
