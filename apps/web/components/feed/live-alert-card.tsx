"use client"

import { cn } from "@/lib/utils"
import type { Alert } from "@/types"
import {
  AlertTriangle,
  ShieldAlert,
  Info,
  CheckCircle2,
  ChevronRight,
} from "lucide-react"

interface LiveAlertCardProps {
  alert: Alert
  onAcknowledge?: (id: string) => void
  onGoToCase?: (id: string) => void
  compact?: boolean
}

const severityConfig = {
  critical: {
    icon: ShieldAlert,
    badge: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
    indicator: "bg-red-500",
    iconColor: "text-red-500",
  },
  high: {
    icon: AlertTriangle,
    badge: "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20",
    indicator: "bg-orange-500",
    iconColor: "text-orange-500",
  },
  medium: {
    icon: AlertTriangle,
    badge: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
    indicator: "bg-amber-500",
    iconColor: "text-amber-500",
  },
  low: {
    icon: CheckCircle2,
    badge: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
    indicator: "bg-emerald-500",
    iconColor: "text-emerald-500",
  },
  info: {
    icon: Info,
    badge: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
    indicator: "bg-blue-500",
    iconColor: "text-blue-500",
  },
}

export function LiveAlertCard({
  alert,
  onAcknowledge,
  onGoToCase,
  compact = false,
}: LiveAlertCardProps) {
  const config = severityConfig[alert.severity]
  const Icon = config.icon

  if (compact) {
    return (
      <div className="flex items-start gap-3 py-3 border-b border-[var(--strix-border)] last:border-0">
        <div className={cn("mt-0.5", config.iconColor)}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-semibold text-[var(--strix-text)] truncate">
              {alert.title}
            </h4>
            <span className="text-[9px] text-[var(--strix-text-muted)] flex-shrink-0">
              {alert.timestamp}
            </span>
          </div>
          <p className="text-[10px] text-[var(--strix-text-muted)] mt-0.5 line-clamp-1">
            {alert.description}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-5 transition-all hover:shadow-md">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-lg",
              config.badge.split(" ").slice(0, 1).join(" "),
              "border",
              config.badge.split(" ").slice(-1).join(" ")
            )}
          >
            <Icon className={cn("h-4 w-4", config.iconColor)} />
          </div>
          <div>
            <span
              className={cn(
                "inline-block px-2 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border mb-1",
                config.badge
              )}
            >
              {alert.category}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-[var(--strix-text-muted)]">
                {alert.timestamp}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <h3 className="text-sm font-bold text-[var(--strix-text)] mb-2">
        {alert.title}
      </h3>
      <p className="text-xs text-[var(--strix-text-muted)] leading-relaxed mb-4">
        {alert.description}
      </p>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {onGoToCase && (
          <button
            onClick={() => onGoToCase(alert.id)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[10px] font-semibold uppercase tracking-wider bg-strix-primary dark:bg-strix-cyan text-white dark:text-strix-bg-dark hover:opacity-90 transition-opacity"
          >
            Go to Case
            <ChevronRight className="h-3 w-3" />
          </button>
        )}
        {onAcknowledge && alert.status === "active" && (
          <button
            onClick={() => onAcknowledge(alert.id)}
            className="px-3 py-1.5 rounded-md text-[10px] font-semibold uppercase tracking-wider border border-[var(--strix-border)] text-[var(--strix-text-muted)] hover:bg-[var(--strix-bg-surface)] transition-colors"
          >
            Acknowledge
          </button>
        )}
      </div>
    </div>
  )
}
