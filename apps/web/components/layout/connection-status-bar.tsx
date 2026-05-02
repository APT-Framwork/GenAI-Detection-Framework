// -----------------------------------------------------------------------------
// connection-status-bar.tsx (Phase 3).
//
// LIVE / RECONNECTING / OFFLINE pill + last-event timestamp. Mounted once in
// the dashboard layout shell so the user always knows whether the multiplexed
// /logs/stream WebSocket is healthy.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useState } from "react";
import { Activity, AlertTriangle, WifiOff } from "lucide-react";
import { useLogStreamConnection } from "@/lib/api/ws";
import { cn } from "@/lib/utils";

type Pill = {
  label: string;
  fg: string;
  bg: string;
  border: string;
  Icon: typeof Activity;
};

const PILLS: Record<"open" | "connecting" | "reconnecting" | "offline", Pill> = {
  open:         { label: "LIVE",         fg: "#10B981", bg: "rgba(16,185,129,0.12)", border: "rgba(16,185,129,0.45)", Icon: Activity },
  connecting:   { label: "CONNECTING",   fg: "#EAB308", bg: "rgba(234,179,8,0.12)",  border: "rgba(234,179,8,0.45)",  Icon: AlertTriangle },
  reconnecting: { label: "RECONNECTING", fg: "#F97316", bg: "rgba(249,115,22,0.12)", border: "rgba(249,115,22,0.45)", Icon: AlertTriangle },
  offline:      { label: "OFFLINE",      fg: "#EF4444", bg: "rgba(239,68,68,0.12)",  border: "rgba(239,68,68,0.45)",  Icon: WifiOff },
};

function formatAge(ms: number): string {
  if (ms < 1000) return "just now";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

export function ConnectionStatusBar({ className }: { className?: string }) {
  const { state, lastEventAt, droppedTotal } = useLogStreamConnection();
  // Tick once a second so "last event 12s ago" updates without socket traffic.
  const [, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const pill = PILLS[state];
  const ageLabel =
    lastEventAt === null ? "no events yet" : `last event ${formatAge(Date.now() - lastEventAt)}`;

  return (
    <div
      className={cn(
        "flex items-center gap-3 text-[11px] uppercase tracking-[0.5px]",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-bold"
        style={{ color: pill.fg, backgroundColor: pill.bg, border: `1px solid ${pill.border}` }}
      >
        <pill.Icon
          size={12}
          className={state === "open" ? "animate-pulse" : undefined}
          aria-hidden
        />
        {pill.label}
      </span>
      <span className="text-[#497f8b] dark:text-[var(--strix-text-muted)]">
        {ageLabel}
      </span>
      {droppedTotal > 0 && (
        <span
          className="rounded px-2 py-0.5 font-semibold"
          style={{ color: "#F97316", backgroundColor: "rgba(249,115,22,0.10)" }}
          title="Frames dropped server-side due to backpressure"
        >
          dropped {droppedTotal}
        </span>
      )}
    </div>
  );
}
