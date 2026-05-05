"use client";

import { useState } from "react";
import {
  CheckCircle2,
  CircleDashed,
  ShieldOff,
  Ban,
  ListChecks,
  Loader2,
} from "lucide-react";
import type { PlaybookStep } from "@/lib/api/playbooks";

const KIND_ICON = {
  manual: ListChecks,
  dqn_override: CheckCircle2,
  isolate_host: ShieldOff,
  block_ip: Ban,
} as const;

const KIND_LABEL = {
  manual: "Manual",
  dqn_override: "Approve DQN",
  isolate_host: "Isolate host",
  block_ip: "Block IP",
} as const;

const KIND_TINT = {
  manual: "text-[#497f8b] dark:text-[var(--strix-text-muted)] border-[rgba(128,182,195,0.25)]",
  dqn_override: "text-[#00666d] dark:text-[#87edf6] border-[#00666d]/30 dark:border-[#87edf6]/30",
  isolate_host: "text-[#b31b25] border-[#b31b25]/30",
  block_ip: "text-amber-600 dark:text-amber-400 border-amber-500/30",
} as const;

interface PlaybookStepCardProps {
  step: PlaybookStep;
  busy: boolean;
  onAct: (step: PlaybookStep) => Promise<void> | void;
}

export function PlaybookStepCard({ step, busy, onAct }: PlaybookStepCardProps) {
  const [done, setDone] = useState(false);
  const Icon = KIND_ICON[step.kind];
  const tint = KIND_TINT[step.kind];

  const handleClick = async () => {
    await onAct(step);
    if (step.kind !== "manual") setDone(true);
  };

  return (
    <div className="group rounded-md border border-[var(--strix-border)] bg-[var(--strix-bg-surface)]/40 p-2.5">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {done ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
          ) : (
            <CircleDashed className="h-3.5 w-3.5" />
          )}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-bold text-[#00343d] dark:text-[var(--strix-text)] leading-snug">
            {step.title}
          </p>
          <p className="text-[10px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5 leading-snug">
            {step.rationale}
          </p>

          {step.kind !== "manual" && (
            <button
              type="button"
              onClick={handleClick}
              disabled={busy || done}
              className={`mt-2 inline-flex items-center gap-1.5 px-2 py-1 rounded border text-[9.5px] font-bold uppercase tracking-wider transition-colors ${tint} hover:bg-[var(--strix-bg-card)] disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {busy ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Icon className="h-3 w-3" />
              )}
              {done ? "Done" : KIND_LABEL[step.kind]}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
