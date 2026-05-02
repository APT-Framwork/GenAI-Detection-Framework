"use client"

import { cn } from "@/lib/utils"
import type { KillChainStage } from "@/types"
import {
  Search,
  Crosshair,
  Send,
  Bug,
  Download,
  Radio,
  Upload,
  Check,
} from "lucide-react"

interface KillChainProgressionProps {
  stages: KillChainStage[]
  /** Drives the header badge: when the chain hasn't actually breached
   *  anything we don't want to scream "BREACH DETECTED" in red. Defaults
   *  to true to preserve callers that pass no flag. */
  isBreach?: boolean
  className?: string
}

const stageIcons = [Search, Crosshair, Send, Bug, Download, Radio, Upload]

export function KillChainProgression({
  stages,
  isBreach = true,
  className,
}: KillChainProgressionProps) {
  return (
    <div className={cn("w-full", className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
          Cyber Kill Chain progression
        </h3>
        {isBreach ? (
          <span className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-[9999px] text-[11px] font-bold bg-red-100 dark:bg-red-500/15 text-[#b31b25] dark:text-red-400 border border-red-200 dark:border-red-500/25 uppercase tracking-wider">
            Breach Detected
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-[9999px] text-[11px] font-bold bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/25 uppercase tracking-wider">
            No breach
          </span>
        )}
      </div>

      {stages.length === 0 && (
        <div className="rounded-xl border border-dashed border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] py-8 text-center text-xs text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          No kill-chain stages recorded for this chain.
        </div>
      )}

      {/* Steps */}
      <div className="flex items-start w-full">
        {stages.map((stage, i) => {
          const isLast = i === stages.length - 1
          const isCompleted = stage.status === "completed"
          const isDetected = stage.status === "detected"
          const isActive = stage.status === "active"
          const isPending = stage.status === "pending"
          const isReached = isCompleted || isDetected || isActive
          const Icon = stageIcons[i] || Search

          return (
            <div
              key={stage.id ?? `stage-${i}`}
              className="flex items-start flex-1 last:flex-none"
            >
              {/* Node + label */}
              <div className="flex flex-col items-center relative min-w-[80px]">
                {/* Circle */}
                <div
                  className={cn(
                    "flex h-12 w-12 items-center justify-center rounded-full border-2 transition-all z-10",
                    isCompleted &&
                      "bg-[#00666d] dark:bg-[#00666d] border-[#00666d]",
                    isDetected &&
                      "bg-[#00666d] dark:bg-[#00666d] border-[#00666d]",
                    isActive &&
                      "bg-[#00666d] dark:bg-[#00666d] border-[#00666d] ring-4 ring-[#87edf6]/30 dark:ring-[#87edf6]/20 animate-pulse-cyan",
                    isPending &&
                      "bg-gray-100 dark:bg-gray-800 border-gray-200 dark:border-gray-700"
                  )}
                >
                  {isCompleted ? (
                    <Check className="h-5 w-5 text-white" />
                  ) : isReached ? (
                    <Icon className="h-5 w-5 text-white" />
                  ) : (
                    <Icon className="h-5 w-5 text-gray-400 dark:text-gray-500" />
                  )}
                </div>

                {/* Label */}
                <span
                  className={cn(
                    "mt-3 text-[10px] font-bold uppercase tracking-wider text-center leading-tight",
                    isReached
                      ? "text-[#00666d] dark:text-[#87edf6]"
                      : "text-gray-400 dark:text-gray-500"
                  )}
                >
                  {stage.name}
                </span>

                {/* Timestamp */}
                {stage.timestamp ? (
                  <span
                    className={cn(
                      "text-[10px] mt-0.5",
                      isReached
                        ? "text-[#497f8b] dark:text-[var(--strix-text-muted)]"
                        : "text-gray-400 dark:text-gray-500"
                    )}
                  >
                    {stage.timestamp}
                  </span>
                ) : (
                  <span className="text-[10px] mt-0.5 text-gray-300 dark:text-gray-600">
                    --:--
                  </span>
                )}

                {/* Active label */}
                {isActive && (
                  <span className="mt-1 text-[9px] font-semibold text-[#b31b25] dark:text-red-400 uppercase tracking-wider">
                    In Progress
                  </span>
                )}
              </div>

              {/* Connector line */}
              {!isLast && (
                <div className="flex-1 h-[3px] mx-1 relative mt-[22px]">
                  <div className="absolute inset-0 bg-gray-200 dark:bg-gray-700 rounded-full" />
                  {isReached && (
                    <div
                      className={cn(
                        "absolute inset-y-0 left-0 rounded-full transition-all duration-500 bg-[#00666d]",
                        stages[i + 1] &&
                          (stages[i + 1].status === "completed" ||
                            stages[i + 1].status === "detected" ||
                            stages[i + 1].status === "active")
                          ? "w-full"
                          : "w-1/2"
                      )}
                    />
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
