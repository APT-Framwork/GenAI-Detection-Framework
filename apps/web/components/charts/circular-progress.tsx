"use client"

import { cn } from "@/lib/utils"

interface CircularProgressProps {
  value: number
  max?: number
  size?: number
  strokeWidth?: number
  label?: string
  sublabel?: string
  className?: string
  color?: string
}

export function CircularProgress({
  value,
  max = 100,
  size = 140,
  strokeWidth = 8,
  label,
  sublabel,
  className,
  color,
}: CircularProgressProps) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const percentage = Math.min(value / max, 1)
  const offset = circumference - percentage * circumference

  const getColor = () => {
    if (color) return color
    if (percentage >= 0.8) return "#EF4444"
    if (percentage >= 0.6) return "#F59E0B"
    if (percentage >= 0.4) return "#0D9488"
    return "#10B981"
  }

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--strix-border)"
          strokeWidth={strokeWidth}
          opacity={0.3}
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={getColor()}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold text-[var(--strix-text)]">
          {Math.round(value)}
        </span>
        {label && (
          <span className="text-[10px] text-[var(--strix-text-muted)] uppercase tracking-wider mt-0.5">
            {label}
          </span>
        )}
        {sublabel && (
          <span className="text-[9px] text-[var(--strix-text-muted)] mt-0.5">
            {sublabel}
          </span>
        )}
      </div>
    </div>
  )
}
