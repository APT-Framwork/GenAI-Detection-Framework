"use client"

// chain-stage-timeline.tsx — chronological list of CKC stage transitions
// for a single chain. Renders the data the live dashboard's APT/RL panels
// don't expose: the wall-clock entry time of each stage and what DQN
// action (if any) was issued in response.

import type { CkcProgressionStep } from "@/lib/api/analysis"
import { cn } from "@/lib/utils"
import { ArrowRight } from "lucide-react"

interface ChainStageTimelineProps {
  stages: CkcProgressionStep[]
  className?: string
}

const ACTION_STYLES: Record<string, string> = {
  NO_OP: "text-[#497f8b] bg-[#497f8b]/10 border-[#497f8b]/20",
  MONITOR: "text-cyan-600 dark:text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
  ESCALATE: "text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20",
  ISOLATE_HOST: "text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/20",
  BLOCK_USER_IP: "text-rose-700 dark:text-rose-300 bg-rose-500/15 border-rose-500/30",
}

function fmt(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

export function ChainStageTimeline({ stages, className }: ChainStageTimelineProps) {
  if (stages.length === 0) {
    return (
      <div className={cn("rounded-xl border border-dashed border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] py-8 text-center text-xs text-[#497f8b] dark:text-[var(--strix-text-muted)]", className)}>
        No stage transitions recorded for this chain yet.
      </div>
    )
  }

  return (
    <ol className={cn("relative space-y-4 pl-6", className)}>
      <span className="absolute left-[7px] top-1 bottom-1 w-px bg-[rgba(128,182,195,0.35)] dark:bg-[var(--strix-border)]" />
      {stages.map((s, i) => {
        const action = s.dqnAction ?? null
        const actionCls = action && ACTION_STYLES[action]
        return (
          <li key={`${s.ckcStage}-${i}`} className="relative">
            <span className="absolute -left-[20px] top-1 h-3.5 w-3.5 rounded-full border-2 border-strix-cyan bg-[var(--strix-bg-card)]" />
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                stage {s.ckcStage}
              </span>
              <span className="text-sm font-bold text-[#00343d] dark:text-[var(--strix-text)]">
                {s.ckcStageName}
              </span>
              <span className="text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                entered {fmt(s.enteredAt)}
              </span>
            </div>
            {action ? (
              <div className="mt-1.5 flex items-center gap-2 text-[11px]">
                <ArrowRight className="h-3 w-3 text-[#497f8b]" />
                <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full font-mono font-semibold border", actionCls ?? "text-[#497f8b] bg-[#497f8b]/10 border-[#497f8b]/20")}>
                  {action}
                </span>
                {s.actionedAt && (
                  <span className="text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                    at {fmt(s.actionedAt)}
                  </span>
                )}
              </div>
            ) : (
              <div className="mt-1.5 text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] italic">
                no STRIX action issued at this stage
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
