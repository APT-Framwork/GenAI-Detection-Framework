"use client"

import { cn } from "@/lib/utils"
import type { TimelineEvent } from "@/types"

interface TimelineChartProps {
  events: TimelineEvent[]
  className?: string
}

const severityDot: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-500",
  medium: "bg-amber-500",
  low: "bg-emerald-500",
  info: "bg-blue-500",
}

export function TimelineChart({ events, className }: TimelineChartProps) {
  return (
    <div className={cn("space-y-0", className)}>
      {events.map((event, i) => (
        <div key={event.id} className="flex gap-3">
          {/* Timeline line */}
          <div className="flex flex-col items-center">
            <div
              className={cn(
                "h-3 w-3 rounded-full mt-1 flex-shrink-0 ring-2 ring-[var(--strix-bg-card)]",
                severityDot[event.severity]
              )}
            />
            {i < events.length - 1 && (
              <div className="w-[2px] flex-1 bg-[var(--strix-border)] my-1" />
            )}
          </div>

          {/* Content */}
          <div className="pb-4 flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-[10px] font-mono text-[var(--strix-text-muted)]">
                {event.timestamp}
              </span>
              <span className="text-[9px] font-semibold uppercase tracking-wider text-strix-primary dark:text-strix-cyan">
                {event.type}
              </span>
            </div>
            <p className="text-xs text-[var(--strix-text)]">
              {event.description}
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}
