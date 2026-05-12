// -----------------------------------------------------------------------------
// playbook-viewer.tsx — collapsible accordion of matched response runbooks
// for an attack chain. Lives in the Attack Analysis right rail.
//
// Steps with kind != 'manual' carry a payload that we POST to either:
//  - `/actions/manual` for `isolate_host` / `block_ip` (operator override)
//  - the existing /actions/{id}/approve flow for `dqn_override` (handled
//    elsewhere — this rail just nudges the operator to the Action Log).
// -----------------------------------------------------------------------------

"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ChevronDown,
  ChevronRight,
  BookOpen,
  ShieldAlert,
  Loader2,
} from "lucide-react";
import {
  type Playbook,
  type PlaybookSeverity,
  type PlaybookStep,
  useManualAction,
  usePlaybooks,
} from "@/lib/api/playbooks";
import { PlaybookStepCard } from "@/components/playbooks/playbook-step";
import { toast } from "@/lib/toast";

const SEVERITY_TINT: Record<PlaybookSeverity, { fg: string; rail: string }> = {
  low:      { fg: "text-emerald-600 dark:text-emerald-400", rail: "bg-emerald-500" },
  medium:   { fg: "text-amber-600 dark:text-amber-400",     rail: "bg-amber-500" },
  high:     { fg: "text-orange-600 dark:text-orange-400",   rail: "bg-orange-500" },
  critical: { fg: "text-[#b31b25]",                         rail: "bg-[#b31b25]" },
};

interface PlaybookViewerProps {
  chainId: string | null;
  stage: number | null;
  technique: string | null;
}

export function PlaybookViewer({ chainId, stage, technique }: PlaybookViewerProps) {
  const q = usePlaybooks({
    stage: stage ?? undefined,
    technique: technique ?? undefined,
    enabled: stage != null || technique != null,
  });
  const manual = useManualAction();

  const matched = q.data?.matched ?? [];
  const fallback = q.data?.fallback ?? null;
  const hasMatched = matched.length > 0;

  return (
    <aside className="bg-[var(--strix-bg-card)] border border-[var(--strix-border)] rounded-xl p-4 sticky top-4 max-h-[calc(100vh-32px)] overflow-y-auto">
      <header className="flex items-center gap-2 mb-3">
        <BookOpen className="h-4 w-4 text-strix-primary dark:text-strix-cyan" />
        <h3 className="text-[12px] font-bold uppercase tracking-wider text-[var(--strix-text)]">
          Response Playbook
        </h3>
        {q.isLoading && <Loader2 className="h-3 w-3 animate-spin text-[var(--strix-text-muted)]" />}
      </header>

      <p className="text-[10px] text-[var(--strix-text-muted)] mb-4">
        Matched against{" "}
        <span className="font-mono">stage {stage ?? "—"}</span>
        {technique && (
          <>
            {" / "}
            <span className="font-mono">{technique}</span>
          </>
        )}
        . <Link href="/actions" className="underline hover:text-[var(--strix-text)]">Action Log →</Link>
      </p>

      {!hasMatched && !fallback && !q.isLoading && (
        <p className="text-[11px] italic text-[var(--strix-text-muted)]">
          No playbook for this combination yet.
        </p>
      )}

      <div className="space-y-2.5">
        {matched.map((pb) => (
          <PlaybookCard
            key={pb.playbookId}
            pb={pb}
            chainId={chainId}
            busy={manual.isPending}
            onAct={async (step) => {
              await runStep({ step, chainId, manual: manual.mutateAsync });
            }}
            startOpen
          />
        ))}
        {fallback && (
          <PlaybookCard
            key={fallback.playbookId}
            pb={fallback}
            chainId={chainId}
            busy={manual.isPending}
            onAct={async (step) => {
              await runStep({ step, chainId, manual: manual.mutateAsync });
            }}
            startOpen={!hasMatched}
            isFallback
          />
        )}
      </div>
    </aside>
  );
}

interface PlaybookCardProps {
  pb: Playbook;
  chainId: string | null;
  busy: boolean;
  onAct: (step: PlaybookStep) => Promise<void>;
  startOpen?: boolean;
  isFallback?: boolean;
}

function PlaybookCard({
  pb,
  chainId,
  busy,
  onAct,
  startOpen = false,
  isFallback = false,
}: PlaybookCardProps) {
  const [open, setOpen] = useState(startOpen);
  const tint = SEVERITY_TINT[pb.severity];

  return (
    <section className="rounded-md border border-[var(--strix-border)] bg-[var(--strix-bg)] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative w-full flex items-start gap-2 text-left px-3 py-2.5 hover:bg-[var(--strix-bg-surface)]/40 transition-colors"
      >
        {/* Severity rail */}
        <span
          className={`absolute left-0 top-0 bottom-0 w-[3px] ${tint.rail}`}
          aria-hidden
        />
        <span className="ml-1 mt-0.5 text-[var(--strix-text-muted)]">
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-[12px] font-bold text-[var(--strix-text)] leading-tight">
              {pb.title}
            </h4>
            {isFallback && (
              <span className="text-[8.5px] uppercase tracking-wider text-[var(--strix-text-muted)] border border-[var(--strix-border)] rounded px-1.5">
                Fallback
              </span>
            )}
            <span className={`text-[9px] uppercase font-bold tracking-wider ml-auto ${tint.fg}`}>
              {pb.severity}
            </span>
          </div>
          <p className="text-[10px] text-[var(--strix-text-muted)] leading-snug mt-0.5">
            {pb.description}
          </p>
        </div>
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 space-y-1.5 border-t border-[var(--strix-border)]/40">
          {pb.steps.map((step) => (
            <PlaybookStepCard
              key={step.stepId}
              step={step}
              busy={busy}
              onAct={onAct}
            />
          ))}
          {!chainId && pb.steps.some((s) => s.payload?.chainIdRequired) && (
            <p className="text-[10px] italic text-amber-600 dark:text-amber-400 mt-1.5 flex items-center gap-1">
              <ShieldAlert className="h-3 w-3" />
              Chain id missing — host-level actions disabled.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

async function runStep({
  step,
  chainId,
  manual,
}: {
  step: PlaybookStep;
  chainId: string | null;
  manual: (b: {
    chainId: string;
    action: number;
    actionName: string;
    reason: string;
  }) => Promise<unknown>;
}): Promise<void> {
  if (step.kind === "manual") return;

  if (step.kind === "dqn_override") {
    toast.info("Open the Action Log to approve pending STRIX actions on this chain.");
    return;
  }

  if (!step.payload || !chainId) {
    toast.warning("Step needs a chain id to run.");
    return;
  }

  // isolate_host or block_ip
  const action = step.payload.action;
  // Map action name → enum int (mirror DqnAction enum).
  const actionInt = mapActionInt(action);
  const reason =
    window.prompt(
      `Reason for ${action} on this chain?`,
      `Playbook: ${step.title}`,
    ) ?? "";
  if (reason.trim().length === 0) return;

  try {
    await manual({
      chainId,
      action: actionInt,
      actionName: action,
      reason: reason.trim(),
    });
    toast.success(`${action} recorded — see Action Log.`);
  } catch (e: unknown) {
    toast.warning(
      `Couldn't record action${e instanceof Error ? `: ${e.message}` : ""}`,
    );
  }
}

function mapActionInt(name: string): number {
  switch (name) {
    case "MONITOR": return 0;
    case "LOW_ALERT": return 1;
    case "ESCALATE": return 2;
    case "ISOLATE_HOST": return 3;
    case "BLOCK_USER_IP": return 4;
    default: return 2;
  }
}
