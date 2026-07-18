// -----------------------------------------------------------------------------
// /hunt — KQL-lite query bar + dense results table + saved queries.
//
// Field operators:  host:  user:  technique:  time:  (free text → ILIKE on full_log)
// Time:             1h | 30m | 24h | 7d | ISO-date
// Quotes work:      host:"db cluster 7"
//
// Permissive parsing — bad input never 400s. Server returns parsed.errors so
// the bar can underline the offending token and execute the rest. Grammar
// mirror lives at apps/web/lib/hunt-grammar.ts (ground truth at
// apps/api/src/strix_api/services/hunt_service.py:parse_query).
//
// Deep-link: /hunt?q=technique:T1059 — driven by the MITRE matrix cell click.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { QueryBar } from "@/components/hunt/query-bar";
import { ResultsTable } from "@/components/hunt/results-table";
import { SavedQueries } from "@/components/hunt/saved-queries";
import {
  useHuntQuery,
  useSaveQuery,
  type HuntResultItem,
} from "@/lib/api/hunt";
import { toast } from "@/lib/toast";

export default function HuntPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initial = searchParams?.get("q") ?? "";

  const [draft, setDraft] = useState(initial);
  const [rows, setRows] = useState<HuntResultItem[]>([]);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  const [activeQ, setActiveQ] = useState(initial);

  const runQuery = useHuntQuery();
  const saveQuery = useSaveQuery();

  const sync = useCallback(
    (q: string) => {
      const sp = new URLSearchParams(searchParams?.toString() ?? "");
      if (q) sp.set("q", q);
      else sp.delete("q");
      const qs = sp.toString();
      router.replace(qs ? `?${qs}` : "?", { scroll: false });
    },
    [router, searchParams],
  );

  const submit = useCallback(
    async (q: string, append = false) => {
      const trimmed = q.trim();
      setActiveQ(trimmed);
      sync(trimmed);
      const result = await runQuery.mutateAsync({
        q: trimmed,
        limit: 100,
        cursor: append ? cursor : null,
      });
      setRows((prev) => (append ? [...prev, ...result.items] : result.items));
      setTotal(result.total);
      setCursor(result.nextCursor);
      setServerErrors(result.parsed.errors);
    },
    [runQuery, cursor, sync],
  );

  // Auto-run on first paint when ?q= is set.
  useEffect(() => {
    if (initial.trim()) {
      void submit(initial, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSave = async () => {
    const q = draft.trim();
    if (!q) return;
    const name = window.prompt("Name this saved query:", suggestName(q));
    if (!name) return;
    try {
      await saveQuery.mutateAsync({ name, q });
      toast.success(`Saved "${name}".`);
    } catch (e) {
      toast.warning("Could not save query.");
    }
  };

  const onRunSaved = (q: string) => {
    setDraft(q);
    void submit(q, false);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-baseline justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[1.2px] text-[#00666d] dark:text-strix-cyan font-bold">
            THREAT HUNTING
          </p>
          <h1 className="text-[24px] font-bold text-[#00343d] dark:text-[var(--strix-text)] tracking-tight font-[family-name:var(--font-space-grotesk)]">
            Hunt
          </h1>
        </div>
        <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {activeQ ? <span className="font-mono">running: <span className="text-[#00343d] dark:text-[var(--strix-text)]">{activeQ}</span></span> : "no active query"}
        </span>
      </div>

      <div className="grid grid-cols-12 gap-5">
        {/* Main column */}
        <div className="col-span-12 lg:col-span-9 space-y-4">
          <div data-tour="hunt-query">
          <QueryBar
            value={draft}
            onChange={setDraft}
            onSubmit={(q) => void submit(q, false)}
            onSave={onSave}
            loading={runQuery.isPending}
            serverErrors={serverErrors}
          />
          </div>

          <ResultsTable
            rows={rows}
            total={total}
            loading={runQuery.isPending}
            hasMore={cursor != null}
            loadMore={() => void submit(activeQ, true)}
          />
        </div>

        {/* Right rail */}
        <div data-tour="hunt-saved" className="col-span-12 lg:col-span-3">
          <SavedQueries onRun={onRunSaved} />
        </div>
      </div>
    </div>
  );
}

function suggestName(q: string): string {
  // Pick the first useful chunk for a default save name.
  const m = /(host|technique|user):([^\s]+)/i.exec(q);
  if (m) return `${m[1]}:${m[2]}`.slice(0, 60);
  return q.slice(0, 60);
}
