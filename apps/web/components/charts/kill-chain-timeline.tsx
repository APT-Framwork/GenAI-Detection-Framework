"use client"

import { cn } from "@/lib/utils"
import type { KillChainStage } from "@/types"

interface KillChainTimelineProps {
  stages: KillChainStage[]
  className?: string
}

const stageColors: Record<KillChainStage["status"], { bg: string; border: string; text: string; dot: string }> = {
  completed: {
    bg: "bg-emerald-500",
    border: "border-emerald-500",
    text: "text-emerald-600 dark:text-emerald-400",
    dot: "bg-emerald-500",
  },
  detected: {
    bg: "bg-amber-500",
    border: "border-amber-500",
    text: "text-amber-600 dark:text-amber-400",
    dot: "bg-amber-500",
  },
  active: {
    bg: "bg-red-500",
    border: "border-red-500",
    text: "text-red-600 dark:text-red-400",
    dot: "bg-red-500 animate-pulse",
  },
  pending: {
    bg: "bg-gray-300 dark:bg-gray-600",
    border: "border-gray-300 dark:border-gray-600",
    text: "text-gray-400 dark:text-gray-500",
    dot: "bg-gray-300 dark:bg-gray-600",
  },
}

export function KillChainTimeline({ stages, className }: KillChainTimelineProps) {
  return (
    <div className={cn("w-full", className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-xs font-semibold text-[var(--strix-text)] uppercase tracking-widest">
          Cyber Kill Chain Progression
        </h3>
        <button className="px-3 py-1 rounded-md text-[10px] font-medium bg-red-500/10 text-red-500 border border-red-500/20 hover:bg-red-500/20 transition-colors">
          BREACH DETECTED
        </button>
      </div>

      {/* Timeline */}
      <div className="flex items-center justify-between relative">
        {/* Connection line */}
        <div className="absolute top-5 left-5 right-5 h-[2px] bg-[var(--strix-border)]" />
        <div
          className="absolute top-5 left-5 h-[2px] bg-strix-primary dark:bg-strix-cyan transition-all duration-700"
          style={{
            width: `${(stages.filter((s) => s.status !== "pending").length / stages.length) * 100}%`,
            maxWidth: "calc(100% - 40px)",
          }}
        />

        {stages.map((stage) => {
          const colors = stageColors[stage.status]
          return (
            <div
              key={stage.id}
              className="relative flex flex-col items-center z-10 group"
            >
              {/* Circle */}
              <div
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all",
                  stage.status === "pending"
                    ? "bg-[var(--strix-bg-surface)] border-gray-300 dark:border-gray-600"
                    : `bg-[var(--strix-bg-card)] ${colors.border}`,
                  stage.status === "active" && "ring-4 ring-red-500/20"
                )}
              >
                <div className={cn("h-3 w-3 rounded-full", colors.dot)} />
              </div>

              {/* Label */}
              <span
                className={cn(
                  "mt-2 text-[9px] font-semibold uppercase tracking-wider text-center",
                  colors.text
                )}
              >
                {stage.name}
              </span>

              {/* Timestamp */}
              {stage.timestamp && (
                <span className="text-[8px] text-[var(--strix-text-muted)] mt-0.5">
                  {stage.timestamp}
                </span>
              )}

              {/* Tooltip on hover */}
              {stage.description && (
                <div className="absolute -bottom-16 left-1/2 -translate-x-1/2 hidden group-hover:block w-48 p-2 rounded-lg bg-[var(--strix-bg-card)] border border-[var(--strix-border)] shadow-lg z-20">
                  <p className="text-[10px] text-[var(--strix-text-muted)] leading-relaxed">
                    {stage.description}
                  </p>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
