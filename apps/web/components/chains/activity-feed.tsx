// activity-feed.tsx — chronological audit log for an attack chain.
//
// Each row decodes the case_audit_log into a small icon + human-readable
// description. The backend's _parse_event() splits to_status into
// (kind, payload); we map kinds → icon + colour here.

"use client";

import { useChainActivity, type ActivityEvent } from "@/lib/api/chains";
import {
  AlertTriangle,
  ArrowRight,
  Crosshair,
  FileText,
  ShieldAlert,
  Tag as TagIcon,
  X,
} from "lucide-react";

function fmtAgo(iso: string) {
  const t = new Date(iso).getTime();
  const diff = (Date.now() - t) / 1000;
  if (diff < 60) return `${Math.max(0, Math.floor(diff))}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

interface Decoded {
  Icon: React.FC<{ className?: string }>;
  iconCls: string;
  label: string;
  detail?: string;
}

function decode(ev: ActivityEvent): Decoded {
  switch (ev.kind) {
    case "triage":
      return {
        Icon: ArrowRight,
        iconCls: "text-[#00666d] dark:text-strix-cyan",
        label: ev.fromStatus
          ? `Triage: ${ev.fromStatus} → ${ev.payload}`
          : `Triage: ${ev.payload}`,
        detail: ev.note ?? undefined,
      };
    case "tag.added":
      return {
        Icon: TagIcon,
        iconCls: "text-[#2a8]",
        label: `Tag added: ${ev.payload}`,
      };
    case "tag.removed":
      return {
        Icon: X,
        iconCls: "text-[#c44]",
        label: `Tag removed: ${ev.payload}`,
      };
    case "tlp":
      return {
        Icon: ShieldAlert,
        iconCls: "text-[#d80]",
        label: `TLP changed: ${ev.payload}`,
      };
    case "note.added":
      return {
        Icon: FileText,
        iconCls: "text-[#497f8b] dark:text-[var(--strix-text-muted)]",
        label: "Analyst note added",
      };
    case "attribution":
      return {
        Icon: Crosshair,
        iconCls: "text-[#c44]",
        label: `Attribution: ${ev.payload}`,
        detail: ev.note ?? undefined,
      };
    default:
      return {
        Icon: AlertTriangle,
        iconCls: "text-[#497f8b]",
        label: `${ev.kind}: ${ev.payload ?? ev.toStatus}`,
      };
  }
}

export function ActivityFeed({ chainId }: { chainId: string }) {
  const { data, isLoading } = useChainActivity(chainId);
  const items = data?.items ?? [];

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-sm font-bold text-[var(--strix-text)]">Activity</h3>
        <span className="text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider">
          audit trail
        </span>
        <span className="ml-auto text-[10px] text-[var(--strix-text-muted)] tabular-nums">
          {items.length} {items.length === 1 ? "event" : "events"}
        </span>
      </div>
      {isLoading ? (
        <p className="text-[11px] text-[var(--strix-text-muted)] italic">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-[11px] text-[var(--strix-text-muted)] italic">
          No activity yet — engine + operator events will appear here.
        </p>
      ) : (
        <ol className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
          {items.map((ev) => {
            const d = decode(ev);
            return (
              <li key={ev.auditId} className="flex items-start gap-2">
                <d.Icon className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${d.iconCls}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] text-[var(--strix-text)] truncate">
                    {d.label}
                  </p>
                  <p className="text-[10px] text-[var(--strix-text-muted)] flex items-center gap-2">
                    <span>{fmtAgo(ev.at)}</span>
                    {ev.userEmail && (
                      <>
                        <span>·</span>
                        <span className="truncate">{ev.userEmail}</span>
                      </>
                    )}
                    {!ev.userEmail && (
                      <>
                        <span>·</span>
                        <span>system</span>
                      </>
                    )}
                  </p>
                  {d.detail && (
                    <p className="text-[10px] text-[var(--strix-text-muted)] italic mt-0.5">
                      {d.detail}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
