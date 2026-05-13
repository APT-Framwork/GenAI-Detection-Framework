"use client"

// chain-stage-timeline.tsx — full kill-chain progression visualisation
// for a single chain. Renders the canonical 8-stage CKC template and
// overlays the chain's actual entries + STRIX actions, so the analyst
// sees both "where this chain has reached" and "what comes next" rather
// than only the stages that have already been entered.

import type { CkcProgressionStep } from "@/lib/api/analysis"
import { cn } from "@/lib/utils"
import { ArrowRight, Check, Circle, Dot } from "lucide-react"

interface ChainStageTimelineProps {
  stages: CkcProgressionStep[]
  className?: string
}

// Canonical CKC stages (must match strix_api.core.enums.kill_chain).
const CKC_TEMPLATE: { stage: number; name: string }[] = [
  { stage: 0, name: "BENIGN" },
  { stage: 1, name: "RECONNAISSANCE" },
  { stage: 2, name: "WEAPONIZATION" },
  { stage: 3, name: "DELIVERY" },
  { stage: 4, name: "EXPLOITATION" },
  { stage: 5, name: "INSTALLATION" },
  { stage: 6, name: "COMMAND_AND_CONTROL" },
  { stage: 7, name: "ACTIONS_ON_OBJECTIVES" },
]

const ACTION_STYLES: Record<string, string> = {
  NO_OP: "text-[#497f8b] bg-[#497f8b]/10 border-[#497f8b]/20",
  MONITOR: "text-cyan-600 dark:text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
  LOW_ALERT: "text-cyan-600 dark:text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
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
  // Group entries by stage so a stage that was re-entered shows every
  // STRIX action issued at it.
  const byStage = new Map<number, CkcProgressionStep[]>()
  for (const s of stages) {
    const arr = byStage.get(s.ckcStage) ?? []
    arr.push(s)
    byStage.set(s.ckcStage, arr)
  }
  const maxReached = stages.reduce((m, s) => Math.max(m, s.ckcStage), -1)

  return (
    <ol className={cn("relative space-y-4 pl-6", className)}>
      <span className="absolute left-[7px] top-1 bottom-1 w-px bg-[rgba(128,182,195,0.35)] dark:bg-[var(--strix-border)]" />
      {CKC_TEMPLATE.map((tmpl) => {
        const entries = byStage.get(tmpl.stage) ?? []
        const entered = entries.length > 0
        const isCurrent = entered && tmpl.stage === maxReached
        const isPast = entered && tmpl.stage < maxReached

        return (
          <li key={tmpl.stage} className="relative">
            <span
              className={cn(
                "absolute -left-[20px] top-1 h-3.5 w-3.5 rounded-full flex items-center justify-center",
                entered
                  ? isCurrent
                    ? "bg-strix-cyan ring-2 ring-strix-cyan/30"
                    : isPast
                      ? "bg-strix-cyan"
                      : "bg-strix-cyan"
                  : "border-2 border-dashed border-[rgba(128,182,195,0.4)] dark:border-[var(--strix-border)] bg-[var(--strix-bg-card)]"
              )}
            >
              {isPast && <Check className="h-2 w-2 text-[var(--strix-bg-card)]" />}
              {isCurrent && <Dot className="h-2 w-2 text-[var(--strix-bg-card)]" />}
              {!entered && <Circle className="h-1 w-1 text-[rgba(128,182,195,0.4)] dark:text-[var(--strix-border)]" />}
            </span>

            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                stage {tmpl.stage}
              </span>
              <span
                className={cn(
                  "text-sm font-bold",
                  entered
                    ? "text-[#00343d] dark:text-[var(--strix-text)]"
                    : "text-[#497f8b] dark:text-[var(--strix-text-muted)]"
                )}
              >
                {tmpl.name}
              </span>
              {entered ? (
                <span className="text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                  entered {fmt(entries[0].enteredAt)}
                </span>
              ) : (
                <span className="text-[10px] font-mono italic text-[#497f8b]/70 dark:text-[var(--strix-text-muted)]/70">
                  not reached
                </span>
              )}
              {isCurrent && (
                <span className="px-1.5 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-wider bg-strix-cyan/15 text-strix-primary dark:text-strix-cyan border border-strix-cyan/30">
                  current
                </span>
              )}
            </div>

            {entered &&
              entries.map((e, i) => {
                const action = e.dqnAction ?? null
                if (!action) {
                  return (
                    <div
                      key={`${tmpl.stage}-${i}-noop`}
                      className="mt-1.5 text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] italic"
                    >
                      no STRIX action issued at this stage
                    </div>
                  )
                }
                const actionCls = ACTION_STYLES[action]
                return (
                  <div key={`${tmpl.stage}-${i}-action`} className="mt-1.5 flex items-center gap-2 text-[11px]">
                    <ArrowRight className="h-3 w-3 text-[#497f8b]" />
                    <span
                      className={cn(
                        "inline-flex items-center px-2 py-0.5 rounded-full font-mono font-semibold border",
                        actionCls ?? "text-[#497f8b] bg-[#497f8b]/10 border-[#497f8b]/20"
                      )}
                    >
                      {action}
                    </span>
                    {e.actionedAt && (
                      <span className="text-[10px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
                        at {fmt(e.actionedAt)}
                      </span>
                    )}
                  </div>
                )
              })}
          </li>
        )
      })}
    </ol>
  )
}
