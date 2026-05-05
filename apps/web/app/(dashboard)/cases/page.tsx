// -----------------------------------------------------------------------------
// /cases — SOC analyst home screen. Triage queue of attack chains.
//
// Linear-style dense table, status rail on the left edge, sticky filter bar
// at the top, sticky bulk-action bar at the bottom when one or more rows
// are selected.
//
// Realtime: subscribes to the SSE live feed; rows whose chainId appears in
// an incoming event flash their status rail for 600 ms. Backend polling at
// 15 s as a backstop in case the SSE is down.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  type TriageStatus,
  useCases,
  useUpdateCaseStatus,
} from "@/lib/api/cases";
import { useLiveFeed } from "@/lib/api/live-feed";
import { CaseRow } from "@/components/cases/case-row";
import { FiltersBar } from "@/components/cases/filters-bar";
import { toast } from "@/lib/toast";
import { Loader2 } from "lucide-react";

export default function CasesPage() {
  const [activeStatus, setActiveStatus] = useState<TriageStatus[]>([]);
  const [minCkc, setMinCkc] = useState(0);
  const [hostQuery, setHostQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const cases = useCases({
    status: activeStatus.length > 0 ? activeStatus : undefined,
    minCkc: minCkc > 0 ? minCkc : undefined,
    limit: 100,
  });

  const items = useMemo(() => {
    const all = cases.data?.items ?? [];
    if (!hostQuery.trim()) return all;
    const q = hostQuery.toLowerCase();
    return all.filter(
      (c) =>
        (c.hostName ?? "").toLowerCase().includes(q) ||
        (c.hostIp ?? "").toLowerCase().includes(q),
    );
  }, [cases.data, hostQuery]);

  // Realtime row flash — when a live-feed event mentions a chainId
  // currently visible, briefly highlight that row's status rail.
  const liveFeed = useLiveFeed({ maxEvents: 50 });
  const [flashSet, setFlashSet] = useState<Set<string>>(new Set());
  const lastSeenLen = useRef(0);
  useEffect(() => {
    if (liveFeed.events.length === lastSeenLen.current) return;
    lastSeenLen.current = liveFeed.events.length;
    const visible = new Set(items.map((c) => c.chainId));
    const fresh = new Set<string>();
    for (const e of liveFeed.events) {
      const cid = e.data.chainId;
      if (cid && visible.has(cid)) fresh.add(cid);
    }
    if (fresh.size === 0) return;
    setFlashSet(fresh);
    const t = setTimeout(() => setFlashSet(new Set()), 600);
    return () => clearTimeout(t);
  }, [liveFeed.events, items]);

  const counts = cases.data?.counts ?? { new: 0, investigating: 0, contained: 0, closed: 0 };

  const toggleStatus = (s: TriageStatus) => {
    setActiveStatus((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
    );
  };
  const clearStatus = () => setActiveStatus([]);

  const toggleSelect = (id: string, on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  };
  const clearSelection = () => setSelected(new Set());

  const updater = useUpdateCaseStatus();
  const bulkSetStatus = async (status: TriageStatus) => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    const results = await Promise.allSettled(
      ids.map((chainId) => updater.mutateAsync({ chainId, body: { status } })),
    );
    const ok = results.filter((r) => r.status === "fulfilled").length;
    const fail = results.length - ok;
    if (ok > 0) toast.success(`Updated ${ok} case${ok === 1 ? "" : "s"} → ${status}.`);
    if (fail > 0) toast.warning(`${fail} update${fail === 1 ? "" : "s"} failed.`);
    clearSelection();
  };

  return (
    <div className="-mx-5 -my-6 flex flex-col h-[calc(100vh-64px)]">
      {/* Header strip — minimal; FiltersBar carries the controls. */}
      <div className="px-5 py-3 border-b border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] flex items-baseline justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[1.2px] text-[#00666d] dark:text-strix-cyan font-bold">
            TRIAGE QUEUE
          </p>
          <h1 className="text-[20px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            Cases
          </h1>
        </div>
        <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] tabular-nums">
          {items.length} of {cases.data?.items.length ?? 0} visible
          {cases.isFetching && (
            <Loader2 className="inline-block ml-2 h-3 w-3 animate-spin" />
          )}
        </span>
      </div>

      <FiltersBar
        active={activeStatus}
        counts={counts}
        onToggle={toggleStatus}
        onClear={clearStatus}
        minCkc={minCkc}
        onMinCkc={setMinCkc}
        hostQuery={hostQuery}
        onHostQuery={setHostQuery}
      />

      {/* Column header (Linear-style dense, sticky just below FiltersBar) */}
      <div className="sticky top-[60px] z-[5] bg-white/80 dark:bg-[var(--strix-bg)]/80 backdrop-blur border-b border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] px-3 py-1.5 flex items-center gap-3 text-[9px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        <span className="ml-3 w-3" aria-hidden />
        <span className="w-[88px]">Chain</span>
        <span className="w-[140px]">Host</span>
        <span className="w-[110px] hidden lg:block">IP</span>
        <span className="w-[88px]">CKC</span>
        <span className="flex-1">Techniques</span>
        <span className="w-[100px] hidden lg:block">Last action</span>
        <span className="w-[40px] text-right">Age</span>
        <span className="w-[28px] text-center">Owner</span>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {cases.isLoading && items.length === 0 ? (
          <EmptyState>Loading triage queue…</EmptyState>
        ) : items.length === 0 ? (
          <EmptyState>
            No cases match the current filters.
          </EmptyState>
        ) : (
          items.map((c) => (
            <CaseRow
              key={c.chainId}
              item={c}
              selected={selected.has(c.chainId)}
              onSelect={toggleSelect}
              flash={flashSet.has(c.chainId)}
            />
          ))
        )}
      </div>

      {/* Bulk action bar (sticky bottom — visible only when ≥ 1 selected). */}
      {selected.size > 0 && (
        <BulkActionBar
          count={selected.size}
          onClear={clearSelection}
          onSet={bulkSetStatus}
          busy={updater.isPending}
        />
      )}
    </div>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-center h-40 text-[12px] italic text-[#497f8b] dark:text-[var(--strix-text-muted)]">
      {children}
    </div>
  );
}

function BulkActionBar({
  count,
  onClear,
  onSet,
  busy,
}: {
  count: number;
  onClear: () => void;
  onSet: (s: TriageStatus) => void;
  busy: boolean;
}) {
  return (
    <div className="sticky bottom-0 z-10 bg-[#00343d] dark:bg-[var(--strix-bg-surface)] border-t border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] px-5 py-3 flex items-center gap-3 shadow-[0_-4px_12px_rgba(0,0,0,0.08)]">
      <span className="text-[12px] font-bold text-white dark:text-[var(--strix-text)] tabular-nums">
        {count} selected
      </span>
      <span className="flex-1" />
      {(["investigating", "contained", "closed"] as TriageStatus[]).map((s) => (
        <button
          key={s}
          type="button"
          disabled={busy}
          onClick={() => onSet(s)}
          className="text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded border border-white/20 text-white hover:bg-white/10 disabled:opacity-50 transition-colors"
        >
          Mark {s}
        </button>
      ))}
      <button
        type="button"
        onClick={onClear}
        className="text-[10px] uppercase tracking-wider text-white/60 hover:text-white px-2"
      >
        Clear
      </button>
    </div>
  );
}
