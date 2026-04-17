import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatNumber(num: number): string {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}k`
  return num.toString()
}

export function formatPercentage(value: number): string {
  return `${value.toFixed(1)}%`
}

export function formatTimestamp(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
}

export function severityColor(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical": return "text-red-500"
    case "high": return "text-orange-500"
    case "medium": return "text-yellow-500"
    case "low": return "text-green-500"
    default: return "text-gray-500"
  }
}

export function severityBgColor(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical": return "bg-red-500/10 border-red-500/30"
    case "high": return "bg-orange-500/10 border-orange-500/30"
    case "medium": return "bg-yellow-500/10 border-yellow-500/30"
    case "low": return "bg-green-500/10 border-green-500/30"
    default: return "bg-gray-500/10 border-gray-500/30"
  }
}
