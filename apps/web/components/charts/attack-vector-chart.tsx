"use client"

import { cn } from "@/lib/utils"

interface AttackVectorData {
  label: string
  value: number
  color: string
}

interface AttackVectorChartProps {
  data?: AttackVectorData[]
  className?: string
}

const defaultData: AttackVectorData[] = [
  { label: "Initial Access", value: 35, color: "#0D9488" },
  { label: "Privilege Escalation", value: 25, color: "#006B94" },
  { label: "Lateral Movement", value: 20, color: "#F59E0B" },
  { label: "Data Exfil", value: 15, color: "#EF4444" },
  { label: "C2 Comms", value: 5, color: "#8A2BE2" },
]

export function AttackVectorChart({ data = defaultData, className }: AttackVectorChartProps) {
  const total = data.reduce((sum, d) => sum + d.value, 0)
  const size = 160
  const strokeWidth = 24
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius

  let currentOffset = 0

  return (
    <div className={cn("flex flex-col items-center", className)}>
      <div className="flex items-center gap-2 mb-4 self-start">
        <h3 className="text-xs font-semibold text-[var(--strix-text)] uppercase tracking-widest">
          Attack Vector Graph
        </h3>
        <div className="flex gap-1">
          <button className="px-2 py-0.5 rounded text-[9px] font-medium bg-strix-primary/10 text-strix-primary dark:bg-strix-cyan/10 dark:text-strix-cyan border border-strix-primary/20 dark:border-strix-cyan/20">
            SHOW TYPE
          </button>
          <button className="px-2 py-0.5 rounded text-[9px] font-medium text-[var(--strix-text-muted)] border border-[var(--strix-border)] hover:bg-[var(--strix-bg-surface)]">
            SORT
          </button>
        </div>
      </div>

      <div className="relative">
        <svg width={size} height={size} className="-rotate-90">
          {data.map((segment) => {
            const segmentLength = (segment.value / total) * circumference
            const gap = 4
            const el = (
              <circle
                key={segment.label}
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke={segment.color}
                strokeWidth={strokeWidth}
                strokeDasharray={`${segmentLength - gap} ${circumference - segmentLength + gap}`}
                strokeDashoffset={-currentOffset}
                strokeLinecap="round"
                className="transition-all duration-500"
                opacity={0.85}
              />
            )
            currentOffset += segmentLength
            return el
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-lg font-bold text-[var(--strix-text)]">{total}</span>
          <span className="text-[9px] text-[var(--strix-text-muted)] uppercase">Vectors</span>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1.5 w-full">
        {data.map((d) => (
          <div key={d.label} className="flex items-center gap-1.5">
            <div
              className="h-2 w-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: d.color }}
            />
            <span className="text-[10px] text-[var(--strix-text-muted)] truncate">
              {d.label}
            </span>
            <span className="text-[10px] font-medium text-[var(--strix-text)] ml-auto">
              {d.value}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
