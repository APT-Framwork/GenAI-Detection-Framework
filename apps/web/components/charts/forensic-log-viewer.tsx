"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import type { LogEntry } from "@/types"
import { Terminal } from "lucide-react"

interface ForensicLogViewerProps {
  logs: LogEntry[]
  className?: string
}

const levelColors: Record<string, string> = {
  AUTH: "text-gray-400",
  WARN: "text-amber-400",
  ERROR: "text-red-400",
  INFO: "text-blue-400",
  ALERT: "text-orange-400",
  BLOCK: "text-red-500",
  STRIX_AI: "text-cyan-400",
  NOTICE: "text-emerald-400",
  PROCESS: "text-purple-400",
  SUCCESS: "text-emerald-400",
  EXEC: "text-amber-400",
  NET: "text-blue-400",
}

const levelBg: Record<string, string> = {
  AUTH: "bg-gray-500/8",
  WARN: "bg-amber-500/8",
  ERROR: "bg-red-500/10",
  INFO: "bg-blue-500/8",
  ALERT: "bg-orange-500/8",
  BLOCK: "bg-red-500/10",
  STRIX_AI: "bg-cyan-500/8",
  NOTICE: "bg-emerald-500/10",
  PROCESS: "bg-purple-500/8",
  SUCCESS: "bg-emerald-500/10",
  EXEC: "bg-amber-500/8",
  NET: "bg-blue-500/8",
}

type FilterType = "all" | "error" | "system"

export function ForensicLogViewer({ logs, className }: ForensicLogViewerProps) {
  const [filter, setFilter] = useState<FilterType>("all")
  const [expanded, setExpanded] = useState(false)

  const filteredLogs =
    filter === "all"
      ? logs
      : filter === "error"
        ? logs.filter(
            (l) => l.level === "ERROR" || l.level === "ALERT" || l.level === "BLOCK"
          )
        : logs.filter(
            (l) =>
              l.level === "PROCESS" ||
              l.level === "INFO" ||
              l.level === "STRIX_AI"
          )

  const displayLogs = expanded ? filteredLogs : filteredLogs.slice(0, 8)

  return (
    <div className={cn("w-full", className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Terminal className="h-4 w-4 text-[#00666d] dark:text-[#87edf6]" />
            <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
              Forensic Raw Logs
            </h3>
          </div>
          <p className="text-[11px] text-[#497f8b] dark:text-[var(--strix-text-muted)] ml-6">
            Direct extraction from ELK-Sentinel stream
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] uppercase tracking-wider font-semibold mr-1">
            Log Filters:
          </span>
          {(
            [
              { key: "all", label: "All Stream" },
              { key: "error", label: "Error only" },
              { key: "system", label: "System Trace" },
            ] as const
          ).map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                "px-3 py-1 rounded-[9999px] text-[10px] font-medium transition-colors",
                filter === f.key
                  ? "bg-[#00666d] text-white dark:bg-[#00666d]"
                  : "text-[#497f8b] dark:text-[var(--strix-text-muted)] border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] hover:bg-gray-50 dark:hover:bg-gray-800"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Log Terminal */}
      <div className="bg-[#0D1117] dark:bg-[#080C14] rounded-[24px] border border-[#1E293B] overflow-hidden">
        {/* Terminal header */}
        <div className="flex items-center gap-1.5 px-5 py-3 border-b border-[#1E293B]">
          <div className="h-3 w-3 rounded-full bg-red-500/70" />
          <div className="h-3 w-3 rounded-full bg-amber-500/70" />
          <div className="h-3 w-3 rounded-full bg-emerald-500/70" />
          <span className="text-[10px] text-gray-500 ml-3 font-mono">
            strix_sentinel_log_stream
          </span>
        </div>

        {/* Log lines */}
        <div className="p-5 max-h-[360px] overflow-y-auto scrollbar-thin font-mono text-[11px] leading-7 space-y-0">
          {displayLogs.map((log, i) => {
            const isHighlighted =
              log.level === "NOTICE" || log.level === "ERROR"
            return (
              <div
                key={i}
                className={cn(
                  "flex gap-4 px-3 py-0.5 rounded-lg transition-colors",
                  isHighlighted
                    ? levelBg[log.level] || ""
                    : "hover:bg-white/[0.03]"
                )}
              >
                <span className="text-gray-500 flex-shrink-0 select-none whitespace-nowrap">
                  {log.timestamp}
                </span>
                <span
                  className={cn(
                    "font-bold flex-shrink-0 min-w-[80px] uppercase",
                    levelColors[log.level] || "text-gray-400"
                  )}
                >
                  {log.level}
                </span>
                <span className="text-gray-300">{log.message}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Load more */}
      <div className="flex justify-center mt-4">
        <button
          onClick={() => setExpanded(!expanded)}
          className="px-6 py-2.5 rounded-[9999px] text-[10px] font-bold uppercase tracking-widest border border-[rgba(128,182,195,0.15)] dark:border-[var(--strix-border)] text-[#497f8b] dark:text-[var(--strix-text-muted)] hover:bg-[#e7faff] dark:hover:bg-[var(--strix-bg-surface)] transition-colors"
        >
          {expanded
            ? "Collapse Logs"
            : `Load Extended Logs (${Math.max(filteredLogs.length - 8, 1420)} Lines)`}
        </button>
      </div>
    </div>
  )
}
