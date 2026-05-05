// -----------------------------------------------------------------------------
// /host/[id] — per-host drill-down. Sticky header (hostname / IP / status /
// summary tiles), tab strip below routed by ?tab= for deep-linkability.
//
// Tab content is alert tables grouped by decoder family + a chains table,
// because raw_jsonb isn't currently persisting structured event data
// (verdicts_writer.py writes `{}`). Once the writer extends raw_jsonb, the
// per-bucket tables can grow to show structured process / network / file
// projections without breaking the response shape.
// -----------------------------------------------------------------------------

"use client";

import { useState, useMemo } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { useHostDetail, type HostDetailResponse } from "@/lib/api/hosts";
import { HostHeader } from "@/components/host/host-header";
import { HostAlertTable } from "@/components/host/host-alert-table";
import { HostChainsTab } from "@/components/host/host-chains-tab";

const TABS = [
  { id: "overview",  label: "Overview" },
  { id: "audit",     label: "Audit" },
  { id: "network",   label: "Network" },
  { id: "files",     label: "Files" },
  { id: "other",     label: "Other" },
  { id: "chains",    label: "Chains" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function HostDetailPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const tabParam = (search?.get("tab") as TabId | null) ?? "overview";
  const [tab, setTab] = useState<TabId>(
    TABS.some((t) => t.id === tabParam) ? tabParam : "overview",
  );

  const q = useHostDetail(params?.id);

  const onTabChange = (next: TabId) => {
    setTab(next);
    const sp = new URLSearchParams(search?.toString() ?? "");
    if (next === "overview") sp.delete("tab");
    else sp.set("tab", next);
    const qs = sp.toString();
    router.replace(qs ? `?${qs}` : "?", { scroll: false });
  };

  if (q.isLoading || !q.data) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-64px)] gap-2 text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-[12px]">Loading host detail…</span>
      </div>
    );
  }

  if (q.isError) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-64px)] text-[12px] text-[#b31b25]">
        Failed to load host detail.
      </div>
    );
  }

  const data = q.data;

  return (
    <div className="-mx-5 -my-6 flex flex-col h-[calc(100vh-64px)]">
      <HostHeader host={data.host} summary={data.summary} />

      <TabStrip tab={tab} onChange={onTabChange} data={data} />

      <div className="flex-1 overflow-y-auto">
        {tab === "overview" && <OverviewTab data={data} onTab={onTabChange} />}
        {tab === "audit"   && <HostAlertTable rows={data.audit}   empty="No audit events for this host in the last 24 hours." />}
        {tab === "network" && <HostAlertTable rows={data.network} empty="No network/web/auth events for this host in the last 24 hours." />}
        {tab === "files"   && <HostAlertTable rows={data.files}   empty="No file integrity events for this host in the last 24 hours." />}
        {tab === "other"   && <HostAlertTable rows={data.other}   empty="No uncategorised alerts for this host in the last 24 hours." />}
        {tab === "chains"  && <HostChainsTab  rows={data.chains} />}
      </div>
    </div>
  );
}

function TabStrip({
  tab,
  onChange,
  data,
}: {
  tab: TabId;
  onChange: (t: TabId) => void;
  data: HostDetailResponse;
}) {
  const counts: Record<TabId, number> = {
    overview: 0,
    audit:    data.audit.length,
    network:  data.network.length,
    files:    data.files.length,
    other:    data.other.length,
    chains:   data.chains.length,
  };

  return (
    <div className="sticky top-[88px] z-[5] bg-white/95 dark:bg-[var(--strix-bg)]/95 backdrop-blur border-b border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] px-5 flex gap-1 overflow-x-auto">
      {TABS.map((t) => {
        const active = t.id === tab;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={`relative px-3 py-2 text-[11px] uppercase tracking-wider font-semibold whitespace-nowrap transition-colors ${
              active
                ? "text-[#00343d] dark:text-[var(--strix-text)]"
                : "text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:text-[#00343d] dark:hover:text-[var(--strix-text)]"
            }`}
          >
            <span className="flex items-center gap-1.5">
              {t.label}
              {t.id !== "overview" && (
                <span className="text-[9px] tabular-nums opacity-70">
                  {counts[t.id]}
                </span>
              )}
            </span>
            {active && (
              <span className="absolute left-2 right-2 -bottom-px h-0.5 bg-[#00666d] dark:bg-[#87edf6] rounded-t" />
            )}
          </button>
        );
      })}
    </div>
  );
}

function OverviewTab({ data, onTab }: { data: HostDetailResponse; onTab: (t: TabId) => void }) {
  const buckets = useMemo(
    () => [
      { id: "audit"   as TabId, label: "Audit",   count: data.audit.length,   hint: "auditd · audit.log" },
      { id: "network" as TabId, label: "Network", count: data.network.length, hint: "web-accesslog · auth.log" },
      { id: "files"   as TabId, label: "Files",   count: data.files.length,   hint: "syscheck" },
      { id: "other"   as TabId, label: "Other",   count: data.other.length,   hint: "uncategorised" },
    ],
    [data],
  );

  const totalChains = data.chains.length;

  return (
    <div className="px-5 py-5 space-y-5">
      {/* Bucket cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {buckets.map((b) => (
          <button
            key={b.id}
            type="button"
            onClick={() => onTab(b.id)}
            className="text-left bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-4 hover:border-[#00666d]/40 dark:hover:border-[#87edf6]/40 transition-colors"
          >
            <p className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              {b.label}
            </p>
            <p className="text-[28px] font-bold text-[#00343d] dark:text-[var(--strix-text)] leading-none mt-1 tabular-nums">
              {b.count}
            </p>
            <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-2">
              {b.hint}
            </p>
          </button>
        ))}
      </div>

      {/* Recent chains preview */}
      <div className="bg-white dark:bg-[var(--strix-bg-card)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] rounded-2xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[12px] font-bold uppercase tracking-wider text-[#00343d] dark:text-[var(--strix-text)]">
            Recent Chains <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)] tabular-nums ml-1">{totalChains}</span>
          </h3>
          <button
            type="button"
            onClick={() => onTab("chains")}
            className="text-[10px] uppercase tracking-wider text-[#00666d] dark:text-[#87edf6] hover:underline"
          >
            View all →
          </button>
        </div>
        {data.chains.length === 0 ? (
          <p className="text-[12px] italic text-[#497f8b] dark:text-[var(--strix-text-muted)]">
            No attack chains touch this host.
          </p>
        ) : (
          <HostChainsTab rows={data.chains.slice(0, 5)} />
        )}
      </div>

      {/* Identity footer */}
      <div className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] flex flex-wrap gap-x-6 gap-y-1">
        <span>first seen <span className="font-mono">{data.host.firstSeenAt || "—"}</span></span>
        <span>last seen <span className="font-mono">{data.host.lastSeenAt || "—"}</span></span>
      </div>
    </div>
  );
}
