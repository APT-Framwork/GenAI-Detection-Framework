// -----------------------------------------------------------------------------
// mitre-coverage-matrix.tsx — 14-tactic ATT&CK coverage heatmap.
//
// Visual idiom: Mandiant-style tactic-column matrix, but with the platform's
// teal → amber → red ramp (severity tokens) instead of Mandiant blue. Cell
// intensity is tinted by `log(count + 1)` so a single hit is visible
// without saturating the whole column when one technique dominates.
//
// Click a cell → /hunt?q=technique:Txxxx (Phase 7 destination — the link
// works ahead of Hunt landing because Next routes 404 quietly until then).
// -----------------------------------------------------------------------------

"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Loader2 } from "lucide-react";
import {
  type TacticCoverage,
  type TechniqueCoverage,
  useMitreCoverage,
} from "@/lib/api/mitre";
import { HoverHelp } from "@/components/ui/hover-help";

// 5-step ramp: teal (cool/coverage) → amber → red (hot/active).
const RAMP = [
  "rgba(135,237,246,0.06)",  // empty
  "rgba(135,237,246,0.18)",  // 1
  "rgba(234,179,8,0.30)",    // few
  "rgba(249,115,22,0.45)",   // many
  "rgba(239,68,68,0.65)",    // hottest
] as const;

function tintFor(count: number, max: number): string {
  if (count <= 0) return RAMP[0];
  if (max <= 1) return RAMP[1];
  // Log-scaled bucket index to reduce dominance of one hot column.
  const f = Math.log(count + 1) / Math.log(max + 1);
  const idx = Math.min(RAMP.length - 1, Math.max(1, Math.round(f * (RAMP.length - 1))));
  return RAMP[idx];
}

function fmtAgo(iso: string | null): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return iso;
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86_400)}d ago`;
}

export function MitreCoverageMatrix() {
  const q = useMitreCoverage();

  const { tactics, globalMax, totalAlerts } = useMemo(() => {
    const ts: TacticCoverage[] = q.data?.tactics ?? [];
    let max = 0;
    let total = 0;
    for (const t of ts) {
      for (const tech of t.techniques) {
        if (tech.count > max) max = tech.count;
        total += tech.count;
      }
    }
    return { tactics: ts, globalMax: max, totalAlerts: total };
  }, [q.data]);

  return (
    <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-5">
      <Header
        windowStart={q.data?.windowStart ?? null}
        windowEnd={q.data?.windowEnd ?? null}
        totalAlerts={totalAlerts}
        otherCount={q.data?.otherCount ?? 0}
        otherIds={q.data?.otherUnmatchedIds ?? []}
        loading={q.isLoading}
      />

      <div className="mt-5 overflow-x-auto">
        <div
          className="grid gap-1.5 min-w-[1280px]"
          style={{ gridTemplateColumns: `repeat(${tactics.length || 14}, minmax(96px, 1fr))` }}
        >
          {tactics.map((t) => (
            <TacticColumn key={t.tacticId} tactic={t} max={globalMax} />
          ))}
        </div>
      </div>

      <Legend max={globalMax} />
    </div>
  );
}

// ── Header ──────────────────────────────────────────────────────────────────

function Header({
  windowStart,
  windowEnd,
  totalAlerts,
  otherCount,
  otherIds,
  loading,
}: {
  windowStart: string | null;
  windowEnd: string | null;
  totalAlerts: number;
  otherCount: number;
  otherIds: string[];
  loading: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3 flex-wrap">
      <div>
        <h2 className="text-[16px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
          ATT&amp;CK Coverage Matrix
          {loading && <Loader2 className="inline-block ml-2 h-3.5 w-3.5 animate-spin" />}
        </h2>
        <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5">
          14 tactics · technique heatmap · last 24 h
          {windowStart && windowEnd && (
            <>
              {" · "}
              <span className="font-mono text-[9px]">
                {fmtTime(windowStart)} → {fmtTime(windowEnd)}
              </span>
            </>
          )}
        </p>
      </div>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        <Pill label="alerts in window" value={totalAlerts.toLocaleString()} />
        {otherCount > 0 && (
          <Pill
            label="catalog drift"
            value={`${otherCount} (${otherIds.length} ids)`}
            warn
            title={otherIds.slice(0, 12).join(", ")}
          />
        )}
      </div>
    </div>
  );
}

function Pill({
  label,
  value,
  warn = false,
  title,
}: {
  label: string;
  value: string;
  warn?: boolean;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] tabular-nums ${
        warn
          ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
          : "border-[rgba(128,182,195,0.25)] dark:border-[var(--strix-border)]"
      }`}
    >
      <span className="opacity-70">{label}</span>
      <span className="font-bold">{value}</span>
    </span>
  );
}

// ── Tactic column ───────────────────────────────────────────────────────────

function TacticColumn({ tactic, max }: { tactic: TacticCoverage; max: number }) {
  // Tactic header tints by its column-total relative to the global max.
  const headerTint = tintFor(tactic.columnTotal, max);
  const isEmpty = tactic.techniques.length === 0;

  return (
    <div className="flex flex-col gap-1">
      <HoverHelp
        title={
          <span className="flex items-center justify-between gap-2">
            <span>{tactic.tacticName}</span>
            <span className="font-mono text-[9px] opacity-70">
              {tactic.tacticId} · CKC {tactic.ckc}
            </span>
          </span>
        }
        body={
          tactic.description || (
            <span className="opacity-70">
              No definition recorded for this tactic in the catalog.
            </span>
          )
        }
        footnote={`${tactic.columnTotal} event${tactic.columnTotal === 1 ? "" : "s"} in window · ${tactic.techniques.length} catalogued technique${tactic.techniques.length === 1 ? "" : "s"}`}
        side="bottom"
        align="start"
        block
        width={320}
      >
        <div
          className="px-2 py-1.5 rounded-md border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] w-full"
          style={{ backgroundColor: headerTint }}
        >
          <p className="text-[9px] uppercase tracking-wider font-bold text-[#00343d] dark:text-[var(--strix-text)] truncate">
            {tactic.tacticName}
          </p>
          <p className="flex items-center justify-between text-[8.5px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5">
            <span className="font-mono">{tactic.tacticId}</span>
            <span className="tabular-nums font-bold">{tactic.columnTotal}</span>
          </p>
        </div>
      </HoverHelp>

      {isEmpty ? (
        <div className="text-[9px] italic text-[#497f8b]/60 dark:text-[var(--strix-text-muted)]/60 px-2 py-3 text-center">
          no observable<br />techniques
        </div>
      ) : (
        tactic.techniques.map((tech) => (
          <TechniqueCell key={`${tactic.tacticId}:${tech.techniqueId}`} tech={tech} max={max} />
        ))
      )}
    </div>
  );
}

function TechniqueCell({
  tech,
  max,
}: {
  tech: TechniqueCoverage;
  max: number;
}) {
  const tint = tintFor(tech.count, max);
  const inactive = tech.count === 0;

  const stats = inactive
    ? "no events in window"
    : `${tech.count} event${tech.count === 1 ? "" : "s"} · ${tech.uniqueHosts} ${tech.uniqueHosts === 1 ? "host" : "hosts"} · last seen ${fmtAgo(tech.lastSeen)}`;

  return (
    <HoverHelp
      title={
        <span className="flex items-center justify-between gap-2">
          <span className="truncate">{tech.techniqueName}</span>
          <span className="font-mono text-[9px] opacity-70">
            {tech.techniqueId}
          </span>
        </span>
      }
      body={
        tech.description || (
          <span className="opacity-70">
            No definition recorded for this technique in the catalog.
          </span>
        )
      }
      footnote={
        <span>
          {stats}
          {" · "}
          <span className="text-strix-cyan">click → /hunt</span>
        </span>
      }
      side="bottom"
      align="start"
      block
      width={320}
    >
      <Link
        href={`/hunt?q=${encodeURIComponent(`technique:${tech.techniqueId}`)}`}
        className="group block px-2 py-1.5 rounded-md border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] hover:border-[#00666d]/50 dark:hover:border-[#87edf6]/50 transition-colors w-full"
        style={{ backgroundColor: tint, opacity: inactive ? 0.5 : 1 }}
      >
        <div className="flex items-baseline justify-between gap-1">
          <span className="font-mono text-[9.5px] font-bold text-[#00343d] dark:text-[var(--strix-text)]">
            {tech.techniqueId}
          </span>
          <span className={`text-[10px] tabular-nums font-bold ${tech.count > 0 ? "text-[#00343d] dark:text-[var(--strix-text)]" : "text-[#497f8b]/60 dark:text-[var(--strix-text-muted)]/60"}`}>
            {tech.count}
          </span>
        </div>
        <p className="text-[9px] leading-tight text-[#00343d]/85 dark:text-[var(--strix-text)]/85 mt-0.5 line-clamp-2 min-h-[20px]">
          {tech.techniqueName}
        </p>
        {tech.count > 0 && (
          <p className="text-[8.5px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-1 flex items-center justify-between">
            <span className="tabular-nums">{tech.uniqueHosts} {tech.uniqueHosts === 1 ? "host" : "hosts"}</span>
            <span>{fmtAgo(tech.lastSeen)}</span>
          </p>
        )}
      </Link>
    </HoverHelp>
  );
}

// ── Legend ──────────────────────────────────────────────────────────────────

function Legend({ max }: { max: number }) {
  return (
    <div className="flex items-center gap-3 mt-4 text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] flex-wrap">
      <span>Cell intensity = log-scaled count vs. max ({max || 0})</span>
      <span className="flex items-center gap-1">
        {RAMP.map((c, i) => (
          <span
            key={i}
            className="h-3 w-5 rounded-sm border border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)]"
            style={{ background: c }}
          />
        ))}
        <span className="ml-1">low → high</span>
      </span>
      <span className="ml-auto">click a cell → /hunt</span>
    </div>
  );
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
