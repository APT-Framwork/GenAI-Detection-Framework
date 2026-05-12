// Shared primitives for the live-inference panels on /ai-engine.
//
// Every model panel uses the same shell: hero header (name + version +
// pulse dot), a hero visualization, and a footer with the latest alert
// ID + age. This file holds the shared building blocks so each panel
// stays a thin component focused on its visualization.

"use client";

import { cn } from "@/lib/utils";

export function PanelShell({
  title,
  subtitle,
  accent,
  active,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  accent: "cyan" | "purple" | "amber" | "emerald" | "rose";
  active: boolean;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const accentMap = {
    cyan:    { bar: "bg-strix-cyan",      dot: "bg-strix-cyan",      glow: "shadow-[0_0_24px_-6px_rgba(135,237,246,0.6)]" },
    purple:  { bar: "bg-purple-500",      dot: "bg-purple-500",      glow: "shadow-[0_0_24px_-6px_rgba(168,85,247,0.6)]" },
    amber:   { bar: "bg-amber-500",       dot: "bg-amber-500",       glow: "shadow-[0_0_24px_-6px_rgba(245,158,11,0.6)]" },
    emerald: { bar: "bg-emerald-500",     dot: "bg-emerald-500",     glow: "shadow-[0_0_24px_-6px_rgba(16,185,129,0.6)]" },
    rose:    { bar: "bg-rose-500",        dot: "bg-rose-500",        glow: "shadow-[0_0_24px_-6px_rgba(244,63,94,0.6)]" },
  }[accent];
  return (
    <div className={cn(
      "relative overflow-hidden rounded-2xl border border-[var(--strix-border)]",
      "bg-[var(--strix-bg-card)] flex flex-col",
      active && accentMap.glow,
      "transition-shadow duration-700",
    )}>
      {/* Accent stripe */}
      <div className={cn("h-0.5 w-full", accentMap.bar, "opacity-80")} />
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <div className="min-w-0">
          <h3 className="text-[13px] font-bold tracking-tight text-[var(--strix-text)] font-[family-name:var(--font-space-grotesk)]">
            {title}
          </h3>
          <p className="text-[9px] uppercase tracking-wider text-[var(--strix-text-muted)] truncate">
            {subtitle}
          </p>
        </div>
        <span
          className={cn(
            "w-1.5 h-1.5 rounded-full shrink-0",
            accentMap.dot,
            active ? "animate-pulse" : "opacity-30",
          )}
          aria-label={active ? "live" : "idle"}
        />
      </div>
      {/* Body */}
      <div className="px-4 pb-3 flex-1 min-h-[180px]">{children}</div>
      {footer && (
        <div className="px-4 pb-3 pt-1 text-[9px] text-[var(--strix-text-muted)] font-mono border-t border-[var(--strix-border)]/30">
          {footer}
        </div>
      )}
    </div>
  );
}

// Tiny horizontal bar with label + value. Used for q-values, neighbor
// risks, etc. Width scales 0..1.
export function MeterRow({
  label,
  value,
  max = 1,
  format = (v) => v.toFixed(2),
  fillCls = "bg-strix-cyan/70",
  highlight = false,
}: {
  label: string;
  value: number | null;
  max?: number;
  format?: (v: number) => string;
  fillCls?: string;
  highlight?: boolean;
}) {
  const v = value ?? 0;
  const pct = Math.max(0, Math.min(100, (v / max) * 100));
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span
        className={cn(
          "w-20 shrink-0 uppercase tracking-wider",
          highlight ? "text-[var(--strix-text)] font-bold" : "text-[var(--strix-text-muted)]",
        )}
      >
        {label}
      </span>
      <div className="flex-1 h-2 rounded-full bg-[var(--strix-bg-deep)] overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-300", fillCls, highlight && "shadow-[0_0_8px_currentColor]")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span
        className={cn(
          "w-12 text-right font-mono tabular-nums",
          highlight ? "text-[var(--strix-text)] font-bold" : "text-[var(--strix-text-muted)]",
        )}
      >
        {value == null ? "—" : format(v)}
      </span>
    </div>
  );
}

// Sparkline — a thin SVG line over the last N samples.
export function Sparkline({
  values,
  max = 1,
  height = 36,
  colour = "#87edf6",
  fillBelow = true,
}: {
  values: number[];
  max?: number;
  height?: number;
  colour?: string;
  fillBelow?: boolean;
}) {
  if (values.length === 0) {
    return (
      <svg viewBox="0 0 100 36" preserveAspectRatio="none" className="w-full" height={height}>
        <line x1={0} y1={18} x2={100} y2={18} stroke="rgba(128,182,195,0.2)" strokeWidth={0.5} strokeDasharray="2 2" />
      </svg>
    );
  }
  const n = values.length;
  const W = 100;
  const H = 36;
  const pts = values.map((v, i) => {
    const x = (i / Math.max(1, n - 1)) * W;
    const y = H - Math.max(0, Math.min(1, v / max)) * H;
    return [x, y] as const;
  });
  const lineD = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const areaD = `${lineD} L ${W},${H} L 0,${H} Z`;
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="w-full"
      height={height}
    >
      {fillBelow && (
        <path d={areaD} fill={colour} fillOpacity={0.12} />
      )}
      <path
        d={lineD}
        fill="none"
        stroke={colour}
        strokeWidth={1.4}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Tip dot for the most recent value */}
      <circle
        cx={pts[pts.length - 1][0]}
        cy={pts[pts.length - 1][1]}
        r={1.6}
        fill={colour}
      />
    </svg>
  );
}

// Big-number hero. Used in every panel for the headline metric.
export function HeroNumber({
  value,
  unit,
  className,
  tone = "default",
}: {
  value: string;
  unit?: string;
  className?: string;
  tone?: "default" | "high" | "mid" | "low";
}) {
  const toneCls = {
    default: "text-[var(--strix-text)]",
    high:    "text-rose-400",
    mid:     "text-amber-400",
    low:     "text-emerald-400",
  }[tone];
  return (
    <div className={cn("flex items-baseline gap-1", className)}>
      <span className={cn(
        "text-[36px] leading-none font-bold tabular-nums font-[family-name:var(--font-space-grotesk)]",
        toneCls,
      )}>
        {value}
      </span>
      {unit && (
        <span className="text-[11px] uppercase tracking-wider text-[var(--strix-text-muted)]">
          {unit}
        </span>
      )}
    </div>
  );
}

export function fmtAgo(iso: string | undefined | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const diff = (Date.now() - t) / 1000;
  if (diff < 60) return `${Math.max(0, Math.floor(diff))}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}
