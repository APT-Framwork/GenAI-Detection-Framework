// -----------------------------------------------------------------------------
// rl-kill-chain.tsx — RL Intervention Timeline (terminal-only).
//
// Sister panel to apt-attack-timeline.tsx. The attack timeline shows live
// chains in progress; THIS panel shows the FROZEN final state of chains
// once they hit a terminal verdict — predetected (agent intervened before
// stage 7) or post-detection (chain reached stage 7). No live animation:
// every card here is the agent's settled outcome on one host.
//
// Per-card rendering:
//   * stage at which the agent intervened → emerald + shield (predetection)
//   * stages reached without intervention → red, with strikethrough on
//     the stages that the agent was too late to prevent
//   * the action the agent recommended (ESCALATE / ISOLATE_HOST / ...)
//   * elapsed-to-detect, last MITRE technique, DQN confidence
//
// This module STILL drains every RL frame and runs the predetection-latch
// logic (it remains the source of truth that writes to the shared
// predetection-store) — it just hides rows whose chain hasn't reached a
// terminal state. Live progression is the APT panel's job.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useLogStream, type RlPayload } from "@/lib/api/ws";
import { useRlTimelineBackfill } from "@/lib/api/analysis";
import { severityColors } from "@/lib/design-tokens";
import { recordPredetection, usePredetections } from "@/lib/predetection-store";
import { HoverHelp } from "@/components/ui/hover-help";

// CKC stage 1..7 — index 0 is "no stage yet" / pre-Recon.
const STAGE_LABELS = [
  "Recon",
  "Weapon",
  "Delivery",
  "Exploit",
  "Install",
  "C2",
  "Action",
] as const;

const ACTION_INTERVENTION_THRESHOLD = 2; // DqnAction.ESCALATE
// Stage 7 = post-detection failure (the chain reached "Action" before the
// agent intervened). Anything ≤ 6 is true predetection. Stages 5–6 (Install /
// C2) are the paper's "critical max" — predetection there is the headline
// case; ≤ 4 is even better. Beyond stage 7 there's nothing left to prevent.
const PREDETECTION_MAX_STAGE = 6;
const PREDETECTION_CRITICAL_MIN = 5;
const TERMINAL_FADE_MS = 10_000;
const TERMINAL_FADE_ANIM_MS = 600; // matches row-fade-out keyframe duration
const MAX_VISIBLE_ROWS = 5;
const COMPLETED_STAGE = 7;

interface RlSession {
  sessionId: string;
  hostId: string | null;
  srcip: string | null;
  currentStage: number; // 1..7, 0 = unknown
  maxStage: number;
  action: number;
  actionName: string;
  confidence: number;
  lastUpdate: number;
  startedAt: number;
  mitigated: boolean;
  completed: boolean;
  terminalAt: number | null; // wall clock when row should be removed
  // Predetection latch — set on the first RL frame that meets the success
  // criteria (action ≥ ESCALATE while maxStage ≤ PREDETECTION_MAX_STAGE).
  // Once set, this row's stage progression is FROZEN: subsequent frames are
  // ignored for currentStage/maxStage updates. The dashboard's whole
  // credibility argument is "the agent intervened HERE and stopped the
  // chain" — letting the timeline keep advancing after that point would
  // contradict the claim.
  predetectionStage: number | null;
  predetectionTechnique: string | null;
  predetectionTactic: string | null;
  predetectionElapsedMs: number | null;
  // Wall-clock TTI — backend-computed (now() at decide minus
  // pipeline_opened_at). Captures the latency our pipeline added.
  predetectionWallElapsedMs: number | null;
  postDetection: boolean; // true if maxStage hit 7 before any intervention
  // Last MITRE tactic / technique observed on ANY frame for this host.
  // Carried across frames so the predetection latch can backfill from
  // memory when the latching frame itself has no MITRE tag (DQN often
  // fires on a non-MITRE event downstream of a tagged one).
  lastSeenTechnique: string | null;
  lastSeenTactic: string | null;
}

function numOr(v: unknown, fallback: number): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

function pickSessionId(p: RlPayload): string | null {
  return (
    (typeof p.host_id === "string" && p.host_id) ||
    (typeof p.srcip === "string" && p.srcip) ||
    (typeof p.agent_id === "string" && p.agent_id) ||
    null
  );
}

interface RlKillChainProps {
  className?: string;
}

export function RlKillChain({ className }: RlKillChainProps) {
  const stream = useLogStream(["rl"]);
  const seq = stream.seq.rl;
  // Predetection-store snapshot — the SAME data the receipts panel renders
  // from. We use it as the single source of truth for predetected rows so
  // the RL Intervention Timeline header counter and the Receipts header
  // counter can never disagree (previously they could: this panel's local
  // sessionsRef would drop entries on remount while the module-level store
  // survived, leaving "2 caught" in receipts but 0 here).
  const predetections = usePredetections();

  const sessionsRef = useRef<Map<string, RlSession>>(new Map());
  const lastSeqRef = useRef(0);
  const [, setTick] = useState(0);

  // Backfill from PG so chains that completed before this widget mounted
  // (or before the WS reconnected) still surface. Live frames remain
  // authoritative — the backfill writes are idempotent and never clobber
  // a richer in-memory session.
  const backfill = useRlTimelineBackfill();
  useEffect(() => {
    if (!backfill.data) return;

    for (const p of backfill.data.predetected) {
      // Key on agent_name so backfill rows merge with live frames (which
      // carry agent_name in `host_id`, not the UUID). Fall back to UUID
      // only when the LEFT JOIN couldn't resolve a host name.
      const hostKey = p.agentName ?? p.hostId;
      const latchedAt = new Date(p.interventionAt).getTime();
      const startedAt = new Date(p.openedAt).getTime();
      recordPredetection({
        hostId: hostKey,
        victimLabel: p.agentName ?? p.hostId,
        stage: p.stageAtDecision || p.maxCkcStage,
        isCritical:
          (p.stageAtDecision || p.maxCkcStage) >= PREDETECTION_CRITICAL_MIN,
        elapsedMs: Math.max(0, latchedAt - startedAt),
        // Wall TTI not derivable from PG backfill (we only persist event-time
        // boundaries on attack_chains). Live frames carry the real value.
        wallElapsedMs: null,
        technique: null,
        tactic: null,
        action: ACTION_INTERVENTION_THRESHOLD,
        actionName: p.actionName,
        confidence: 0,
        latchedAt,
      });
    }

    for (const c of backfill.data.post_detected) {
      const id = c.agentName ?? c.hostId;
      const existing = sessionsRef.current.get(id);
      // Don't clobber a session already at terminal — live frames carry
      // richer data (action, confidence, technique). Only fill the gap.
      if (existing && existing.maxStage >= COMPLETED_STAGE) continue;
      const closedAtMs = c.closedAt ? new Date(c.closedAt).getTime() : Date.now();
      sessionsRef.current.set(id, {
        sessionId: id,
        hostId: id,
        srcip: existing?.srcip ?? null,
        currentStage: c.maxCkcStage,
        maxStage: c.maxCkcStage,
        action: existing?.action ?? 0,
        actionName: existing?.actionName ?? "",
        confidence: existing?.confidence ?? 0,
        lastUpdate: closedAtMs,
        startedAt: new Date(c.openedAt).getTime(),
        mitigated: existing?.mitigated ?? false,
        completed: true,
        terminalAt: null,
        predetectionStage: null,
        predetectionTechnique: existing?.predetectionTechnique ?? null,
        predetectionTactic: existing?.predetectionTactic ?? null,
        predetectionElapsedMs: existing?.predetectionElapsedMs ?? null,
        predetectionWallElapsedMs: existing?.predetectionWallElapsedMs ?? null,
        postDetection: true,
        lastSeenTechnique: existing?.lastSeenTechnique ?? null,
        lastSeenTactic: existing?.lastSeenTactic ?? null,
      });
    }
    setTick((n) => n + 1);
  }, [backfill.data]);

  // Drain RL frames into per-session accumulator.
  useEffect(() => {
    if (seq <= lastSeqRef.current) return;
    const buf = stream.frames.rl;
    const fresh = buf.slice(buf.length - (seq - lastSeqRef.current));
    lastSeqRef.current = seq;

    const map = sessionsRef.current;
    const now = Date.now();
    for (const env of fresh) {
      const p = env.payload;
      const id = pickSessionId(p);
      if (!id) continue;

      // Pick the deepest stage signal available on the frame. Backend now
      // sends three: `transformer_pred_ckc`, `mitre_ckc_stage`,
      // `chain_max_ckc_stage`. Older frames only carry `ckc_stage` so fall
      // back to that. The Transformer alone collapses to ~Delivery on lab
      // data; MITRE-tagged + chain-running-max give the true progression.
      const transformerPred = numOr(p.transformer_pred_ckc, 0);
      const mitreCkc = numOr(p.mitre_ckc_stage, 0);
      const chainMax = numOr(p.chain_max_ckc_stage, 0);
      const ckcStageRaw = numOr(p.ckc_stage, 0);
      const stage = Math.max(transformerPred, mitreCkc, chainMax, ckcStageRaw);
      const action = typeof p.action === "number" ? p.action : 0;
      const actionName = typeof p.action_name === "string" ? p.action_name : "";
      const confidence = typeof p.confidence === "number" ? p.confidence : 0;

      const tactics = Array.isArray(p.mitre_tactics) ? p.mitre_tactics : [];
      const techniques = Array.isArray(p.mitre_techniques) ? p.mitre_techniques : [];
      const frameTechnique = techniques.length > 0 ? techniques[techniques.length - 1] : null;
      const frameTactic = tactics.length > 0 ? tactics[tactics.length - 1] : null;

      const existing = map.get(id);
      // Carry technique/tactic across frames — a latch frame often lacks
      // MITRE tags but a previous frame for the same host did. Use the
      // current frame's value if non-null, else preserve what we knew.
      const lastSeenTechnique = frameTechnique ?? existing?.lastSeenTechnique ?? null;
      const lastSeenTactic = frameTactic ?? existing?.lastSeenTactic ?? null;
      const wasPredetected = existing?.predetectionStage != null;
      const wasTerminal = existing?.terminalAt != null;

      // Predetection latch is sticky: once set, the row freezes. Keep the
      // existing maxStage/currentStage and ignore further bumps.
      const observedMax = Math.max(existing?.maxStage ?? 0, stage, chainMax);
      const maxStage = wasPredetected ? existing!.maxStage : observedMax;
      const currentStage = wasPredetected ? existing!.currentStage : stage;

      const intervened = action >= ACTION_INTERVENTION_THRESHOLD;
      const mitigated = (existing?.mitigated ?? false) || intervened;
      const completed = (existing?.completed ?? false) || maxStage >= COMPLETED_STAGE;

      // Decide whether THIS frame is the predetection event.
      let predetectionStage = existing?.predetectionStage ?? null;
      let predetectionTechnique = existing?.predetectionTechnique ?? null;
      let predetectionTactic = existing?.predetectionTactic ?? null;
      let predetectionElapsedMs = existing?.predetectionElapsedMs ?? null;
      let predetectionWallElapsedMs = existing?.predetectionWallElapsedMs ?? null;
      let postDetection = existing?.postDetection ?? false;
      // Prefer backend-derived timing over browser-side wall-clock so a
      // chain whose first RL frame is already ESCALATE doesn't report 0 ms
      // (it just means we hadn't seen the session before — not that the
      // agent reacted instantly).
      const backendTtiMs =
        typeof p.time_to_intervene_ms === "number" && p.time_to_intervene_ms >= 0
          ? p.time_to_intervene_ms
          : null;
      const backendWallTtiMs =
        typeof p.wall_time_to_intervene_ms === "number" &&
        p.wall_time_to_intervene_ms >= 0
          ? p.wall_time_to_intervene_ms
          : null;
      const backendOpenedAtMs =
        typeof p.chain_opened_at === "string" && p.chain_opened_at
          ? new Date(p.chain_opened_at).getTime()
          : null;
      if (!wasPredetected) {
        const candidateMax = observedMax;
        if (intervened && candidateMax > 0 && candidateMax <= PREDETECTION_MAX_STAGE) {
          // Latch. Use carried-over technique/tactic so the receipt
          // doesn't render a "—" when the DQN fired on a frame that had
          // no MITRE tag itself (very common — Caldera tactics emit
          // tagged events sparsely among generic auditd noise).
          predetectionStage = candidateMax;
          predetectionTechnique = lastSeenTechnique;
          predetectionTactic = lastSeenTactic;
          if (backendTtiMs != null) {
            // Authoritative: backend computed delta of two Wazuh
            // occurred_at timestamps. No clock skew, no browser fallback.
            predetectionElapsedMs = backendTtiMs;
          } else {
            // Last-resort fallback when the worker hasn't shipped the
            // backend timing yet (older payloads or pre-restart sessions).
            const startedAt = existing?.startedAt ?? now;
            predetectionElapsedMs = Math.max(0, now - startedAt);
          }
          // Wall TTI is only authoritative if the backend supplied it.
          // No browser fallback — `Date.now()` here would be the time we
          // first saw an RL frame for this host, which has nothing to do
          // with when the worker actually opened the chain.
          predetectionWallElapsedMs = backendWallTtiMs;

          const hostKey = (typeof p.host_id === "string" && p.host_id) || id;
          const victimLabel =
            (typeof p.host_id === "string" && p.host_id) ||
            (typeof p.srcip === "string" && p.srcip) ||
            id;
          recordPredetection({
            hostId: hostKey,
            victimLabel,
            stage: candidateMax,
            isCritical: candidateMax >= PREDETECTION_CRITICAL_MIN,
            elapsedMs: predetectionElapsedMs,
            wallElapsedMs: predetectionWallElapsedMs,
            technique: lastSeenTechnique,
            tactic: lastSeenTactic,
            action,
            actionName,
            confidence,
            latchedAt: now,
          });
        } else if (observedMax >= COMPLETED_STAGE) {
          // Chain hit Action without an intervention — record the post-
          // detection failure so the row colour-codes correctly.
          postDetection = true;
        }
      }

      // Predetected rows stay visible — the proof IS the row. Only fade
      // on completed (post-detection failure) or plain mitigated chains
      // that didn't latch a predetection.
      const shouldFade = (mitigated || completed) && predetectionStage == null;
      const terminalAt = wasTerminal
        ? existing!.terminalAt
        : shouldFade
          ? now + TERMINAL_FADE_MS
          : null;

      map.set(id, {
        sessionId: id,
        hostId: (typeof p.host_id === "string" ? p.host_id : existing?.hostId) ?? null,
        srcip: (typeof p.srcip === "string" ? p.srcip : existing?.srcip) ?? null,
        currentStage,
        maxStage,
        action: wasPredetected ? existing!.action : action,
        actionName: wasPredetected ? existing!.actionName : actionName,
        confidence: wasPredetected ? existing!.confidence : confidence,
        lastUpdate: now,
        // Prefer the backend chain-open timestamp for the same reason as
        // the elapsed calculation above — Wazuh occurred_at is the only
        // reference that's stable across browser clocks.
        startedAt: existing?.startedAt ?? backendOpenedAtMs ?? now,
        mitigated,
        completed,
        terminalAt,
        predetectionStage,
        predetectionTechnique,
        predetectionTactic,
        predetectionElapsedMs,
        predetectionWallElapsedMs,
        postDetection,
        lastSeenTechnique,
        lastSeenTactic,
      });
    }
    setTick((n) => n + 1);
  }, [seq, stream.frames.rl]);

  // 1 Hz tick to drive the fade-out countdown + actually evict expired rows.
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      const map = sessionsRef.current;
      const toDelete: string[] = [];
      map.forEach((s, id) => {
        if (s.terminalAt != null && now > s.terminalAt + TERMINAL_FADE_ANIM_MS) {
          toDelete.push(id);
        }
      });
      for (const id of toDelete) map.delete(id);
      // Even with no eviction, re-render so the fade-out class can mount on
      // sessions whose terminalAt just passed.
      setTick((n) => n + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Terminal sessions: predetected rows are the predetection-store's
  // truth (same data the Receipts panel shows — guarantees the two
  // counters agree); post-detected rows come from local sessionsRef.
  const terminalSessions = useMemo(() => {
    const out: RlSession[] = [];

    // 1) Predetections — synthesise an RlSession from each store entry,
    //    overlaying any extra fields we may already have locally.
    for (const p of Array.from(predetections.values())) {
      const local = sessionsRef.current.get(p.hostId);
      out.push({
        sessionId: p.hostId,
        hostId: p.hostId,
        srcip: local?.srcip ?? null,
        currentStage: p.stage,
        maxStage: p.stage,
        action: p.action,
        actionName: p.actionName,
        confidence: p.confidence,
        lastUpdate: p.latchedAt,
        startedAt: local?.startedAt ?? p.latchedAt - p.elapsedMs,
        mitigated: true,
        completed: false,
        terminalAt: null,
        predetectionStage: p.stage,
        predetectionTechnique: p.technique,
        predetectionTactic: p.tactic,
        predetectionElapsedMs: p.elapsedMs,
        predetectionWallElapsedMs: p.wallElapsedMs,
        postDetection: false,
        lastSeenTechnique: p.technique,
        lastSeenTactic: p.tactic,
      });
    }

    // 2) Post-detected rows — sessions that ran the full chain to stage 7
    //    without being latched. Skip any host already covered above.
    for (const s of Array.from(sessionsRef.current.values())) {
      if (s.predetectionStage != null) continue;
      if (predetections.has(s.hostId ?? s.sessionId)) continue;
      if (s.maxStage >= COMPLETED_STAGE) out.push(s);
    }

    return out.sort((a, b) => {
      const aP = a.predetectionStage != null ? 0 : 1;
      const bP = b.predetectionStage != null ? 0 : 1;
      if (aP !== bP) return aP - bP;
      return b.lastUpdate - a.lastUpdate;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seq, sessionsRef.current.size, predetections]);

  const visible = terminalSessions.slice(0, MAX_VISIBLE_ROWS);
  const overflow = Math.max(0, terminalSessions.length - visible.length);

  const predetectionCount = useMemo(
    () => terminalSessions.filter((s) => s.predetectionStage != null).length,
    [terminalSessions],
  );
  const postDetectionCount = terminalSessions.length - predetectionCount;

  return (
    <div className={cn("w-full", className)}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
            RL Intervention Timeline
          </h3>
          <p className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5">
            frozen final state — agent verdict per chain
          </p>
        </div>
        <div className="flex items-center gap-3 text-[10px] uppercase tracking-wider">
          <HoverHelp
            title="Predetected"
            body={
              <>
                Chains where the agent fired <strong>ESCALATE</strong>{" "}
                (DQN action ≥ 2) while the chain&apos;s deepest stage was ≤
                6. The intervention happened <em>before</em> stage 7
                (Action) — the success case.
              </>
            }
            align="end"
          >
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
              {predetectionCount} predetected
            </span>
          </HoverHelp>
          <HoverHelp
            title="Post-detected"
            body={
              <>
                Chains that ran the full kill-chain to stage{" "}
                <strong>7 (Action)</strong> without an intervention. The
                agent caught it too late — these are the failures the
                predetection metric is designed to drive down.
              </>
            }
            align="end"
          >
            <span className="text-rose-500 font-semibold">
              {postDetectionCount} post-detected
            </span>
          </HoverHelp>
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[rgba(128,182,195,0.3)] dark:border-[var(--strix-border)] py-8 text-center text-xs text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          No verdicts yet.
          <br />
          <span className="text-[9px]">
            (active chains are shown in the APT Attack Timeline; cards land
            here once the agent intervenes or the chain hits stage 7)
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {visible.map((s) => (
            <SessionRow key={s.sessionId} session={s} />
          ))}
        </div>
      )}

      {overflow > 0 && (
        <div className="mt-3 text-center text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          + {overflow} more verdict{overflow === 1 ? "" : "s"}
        </div>
      )}
    </div>
  );
}

function SessionRow({ session: s }: { session: RlSession }) {
  const isFading = s.terminalAt != null && Date.now() >= s.terminalAt;
  const label = s.hostId ?? s.srcip ?? s.sessionId;
  const predetected = s.predetectionStage != null;
  // Event-time TTI (predetected) or time-since-start (live). Sub-second
  // values were rounding to "0s" before — show ms when < 1s so the panel
  // can demonstrate the agent reacted in tens of milliseconds.
  const elapsedMs = predetected
    ? Math.max(0, s.predetectionElapsedMs ?? 0)
    : Math.max(0, Date.now() - s.startedAt);
  const elapsedLabel = formatTtiLabel(elapsedMs);
  // Wall-clock TTI — only meaningful when backend supplied it (live frames).
  // PG-backfilled rows have wallElapsedMs = null and we hide that badge.
  const wallElapsedMs = predetected ? s.predetectionWallElapsedMs : null;
  const wallElapsedLabel =
    wallElapsedMs != null ? formatTtiLabel(wallElapsedMs) : null;

  // State label priority: predetection > post-detection failure > generic.
  const stateLabel = predetected
    ? `PREDETECTED · ${STAGE_LABELS[s.predetectionStage! - 1]}`
    : s.postDetection
      ? "POST-DETECTION"
      : s.mitigated
        ? "MITIGATED"
        : s.completed
          ? "COMPLETED"
          : s.currentStage >= 1
            ? `Stage ${s.currentStage}`
            : "PENDING";
  const stateSev = predetected
    ? "low"
    : s.postDetection
      ? "critical"
      : s.mitigated
        ? "low"
        : s.completed
          ? "critical"
          : stageSeverity(s.currentStage);
  const stateColors = severityColors[stateSev];

  return (
    <div
      className={cn(
        "rounded-xl border p-3",
        predetected
          ? "border-emerald-500/40 bg-emerald-500/5 dark:bg-emerald-500/[0.04] shadow-[0_0_0_1px_rgba(34,197,94,0.18)_inset]"
          : "border-[rgba(128,182,195,0.2)] dark:border-[var(--strix-border)] bg-[var(--strix-bg-card)] dark:bg-[var(--strix-bg-surface)]",
        "animate-slide-up-in",
        isFading && "animate-row-fade-out",
      )}
    >
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] font-mono font-bold text-[#00343d] dark:text-[var(--strix-text)] truncate">
            {label}
          </span>
          {s.actionName && (
            <span className="text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              {s.actionName}
            </span>
          )}
          {predetected && (
            <HoverHelp
              title="Chain frozen"
              body={
                <>
                  Once the agent fired <strong>ESCALATE</strong> we stop
                  advancing this row&apos;s stage progression — the row is the
                  proof. Any further attacker noise on the same host is
                  ignored client-side.
                </>
              }
              footnote="dashboard-only freeze; Caldera continues running in the lab"
              align="start"
            >
              <span className="text-[9px] font-mono text-emerald-600 dark:text-emerald-400">
                ⛨ chain frozen
              </span>
            </HoverHelp>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <HoverHelp
            title="Verdict"
            body={
              predetected ? (
                <>
                  Agent intervened at stage{" "}
                  <strong>{s.predetectionStage}</strong> (
                  {STAGE_LABELS[s.predetectionStage! - 1]}). Stages 1–
                  {s.predetectionStage} were observed; stages{" "}
                  {(s.predetectionStage as number) + 1}–7 prevented.
                </>
              ) : s.postDetection ? (
                <>
                  Chain reached stage <strong>7 (Action)</strong> before any
                  ESCALATE — the agent caught it too late. This is the
                  failure case the predetection metric is designed to avoid.
                </>
              ) : (
                <>
                  Active chain at stage{" "}
                  <strong>{s.currentStage || "—"}</strong>. Will land here as
                  PREDETECTED or POST-DETECTION once the agent decides or
                  the chain hits stage 7.
                </>
              )
            }
          >
            <span
              className="px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider border"
              style={{
                color: stateColors.fg,
                background: stateColors.bg,
                borderColor: stateColors.border,
              }}
            >
              {stateLabel}
            </span>
          </HoverHelp>
          <HoverHelp
            title="Transformer confidence"
            body={
              <>
                Softmax max over the 8-class CKC head at the moment of
                latch. <strong>Not</strong> the DQN&apos;s confidence — the
                DQN emits Q-values, not probabilities. Useful as a signal
                quality proxy on the upstream classifier.
              </>
            }
          >
            <span className="text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              {(s.confidence * 100).toFixed(0)}%
            </span>
          </HoverHelp>
          {predetected ? (
            <>
              <HoverHelp
                title="Event-time TTI"
                body={
                  <>
                    Gap between two Wazuh <code>occurred_at</code>{" "}
                    timestamps: the alert that <em>opened</em> the chain →
                    the alert that triggered <strong>ESCALATE</strong>. Tells
                    you <em>how deep into the chain</em> the agent fired.
                    Not affected by pipeline latency.
                  </>
                }
                footnote="ms when < 1s · pure event-time"
                align="end"
              >
                <span className="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold border border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 tabular-nums">
                  ⏱ evt {elapsedLabel}
                </span>
              </HoverHelp>
              {wallElapsedLabel != null && (
                <HoverHelp
                  title="Wall-clock TTI"
                  body={
                    <>
                      Server clock at decide-time minus server clock when we
                      opened the chain. Captures end-to-end pipeline
                      latency: <code>Filebeat → OpenSearch → ingest →
                      inference</code>. This is the &quot;real time the
                      system took to stop it&quot; metric.
                    </>
                  }
                  footnote="not available on PG-backfilled rows"
                  align="end"
                >
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold border border-strix-cyan/40 bg-strix-cyan/10 text-strix-cyan tabular-nums">
                    ⏱ wall {wallElapsedLabel}
                  </span>
                </HoverHelp>
              )}
            </>
          ) : (
            <span className="text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
              {elapsedLabel} live
            </span>
          )}
        </div>
      </div>

      <StageBar session={s} />

      {predetected && (
        <div className="mt-2 flex items-center gap-2 text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
            agent intervened in {elapsedLabel}
            {wallElapsedLabel != null ? ` (wall ${wallElapsedLabel})` : ""} →
          </span>
          {s.predetectionTechnique && (
            <HoverHelp
              title="Last MITRE technique"
              body={
                <>
                  The most recent MITRE-ATT&amp;CK technique tag observed on
                  this host before the agent latched. Frames at the latch
                  moment often carry no MITRE tag (DQN fires on a non-tagged
                  downstream event), so we backfill from the last tagged
                  frame in the chain.
                </>
              }
            >
              <span className="text-[#00343d] dark:text-[var(--strix-text)]">
                {s.predetectionTechnique}
              </span>
            </HoverHelp>
          )}
          {s.predetectionTactic && (
            <span className="opacity-70">[{s.predetectionTactic}]</span>
          )}
          <HoverHelp
            title="Stages prevented"
            body={
              <>
                Because the agent intervened at stage{" "}
                <strong>{s.predetectionStage}</strong>, stages{" "}
                {(s.predetectionStage as number) + 1}–7 were never reached
                in this chain — counterfactually, those would have been{" "}
                <code>C2</code> / <code>Action</code> activity. This is the
                paper&apos;s &quot;predetection success&quot; case.
              </>
            }
            align="end"
            className="ml-auto"
          >
            <span className="text-emerald-500/80">
              stage 7 (Action) prevented
            </span>
          </HoverHelp>
        </div>
      )}
    </div>
  );
}

function StageBar({ session: s }: { session: RlSession }) {
  // Progress fill goes from node 1 to currentStage's center.
  const W = 560;
  const H = 44;
  const padX = 16;
  const slotCount = STAGE_LABELS.length;
  const slotWidth = (W - 2 * padX) / (slotCount - 1);
  const cy = H / 2;

  const reached = Math.max(0, Math.min(7, s.maxStage));
  const current = Math.max(0, Math.min(7, s.currentStage));
  const fillEndX = padX + Math.max(0, current - 1) * slotWidth;

  return (
    <svg
      className="w-full"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="kill-chain progress"
    >
      {/* Track */}
      <line
        x1={padX}
        y1={cy}
        x2={W - padX}
        y2={cy}
        stroke="rgba(128,182,195,0.25)"
        strokeWidth={3}
        strokeLinecap="round"
      />
      {/* Progress fill — pre-latch portion is RED (attacker traversed
          these stages unimpeded; agent missed); switches at the latch
          stage; post-latch ghost line below is GREEN (prevented). */}
      {reached > 0 && (
        <line
          x1={padX}
          y1={cy}
          x2={
            padX +
            Math.max(0, (s.predetectionStage ?? reached) - 1) * slotWidth
          }
          y2={cy}
          stroke={
            s.predetectionStage != null
              ? "#EF4444"
              : s.mitigated
                ? severityColors.low.fg
                : "#F59E0B"
          }
          strokeWidth={3}
          strokeLinecap="round"
          style={{ transition: "x2 300ms ease, stroke 300ms ease" }}
        />
      )}
      {/* Ghost track from latch → end (the "prevented" portion — defender
          wins, never actually happened). */}
      {s.predetectionStage != null && s.predetectionStage < 7 && (
        <line
          x1={padX + (s.predetectionStage - 1) * slotWidth}
          y1={cy}
          x2={W - padX}
          y2={cy}
          stroke="rgba(16,185,129,0.4)"
          strokeWidth={2}
          strokeDasharray="4 3"
          strokeLinecap="round"
        />
      )}

      {STAGE_LABELS.map((label, i) => {
        const stageIndex = i + 1;
        const cx = padX + i * slotWidth;
        const past = stageIndex < current;
        const isCurrent = stageIndex === current && !s.mitigated && !s.completed;
        const future = stageIndex > reached;
        const predetected = s.predetectionStage != null;
        const isLatchStage = predetected && stageIndex === s.predetectionStage;
        // After predetection, stages > predetection stage are "prevented" —
        // render them as ghosted, dashed, red-tinted to convey "this would
        // have happened if the agent hadn't intervened."
        const isPrevented = predetected && stageIndex > s.predetectionStage!;

        let fill = "rgba(128,182,195,0.18)";
        let stroke = "rgba(128,182,195,0.45)";
        let textColor = "#497f8b";
        let dashed = false;
        if (isPrevented) {
          // Stages AFTER the latch — never happened. Defender wins.
          // Ghosted green + dashed border conveys "prevented, didn't occur".
          fill = "rgba(16,185,129,0.08)";
          stroke = "rgba(16,185,129,0.5)";
          textColor = "rgba(16,185,129,0.75)";
          dashed = true;
        } else if (isLatchStage) {
          fill = "#10B981";
          stroke = "#34D399";
          textColor = "#10B981";
        } else if (predetected && stageIndex < s.predetectionStage!) {
          // Pre-latch stages — attacker traversed unimpeded, agent missed.
          // Render same amber→red gradient as a post-detection chain so the
          // visual matches the truth: these stages happened on the host.
          const t = stageIndex / 7;
          fill = lerpHex("#F59E0B", "#EF4444", t);
          stroke = fill;
          textColor = "#EF4444";
        } else if (s.mitigated && stageIndex <= reached && !s.completed) {
          // Mid-chain mitigation (action ≥ ESCALATE before stage 7).
          // Post-detection (chain hit stage 7) falls through to the
          // amber→red gradient below — rendering all-green checkmarks
          // on a chain that ran the full 7 stages would communicate
          // "success" when the truth is "we caught it too late."
          fill = severityColors.low.fg;
          stroke = severityColors.low.fg;
          textColor = "#0b1416";
        } else if (past || (stageIndex <= reached && !future)) {
          const t = stageIndex / 7;
          fill = lerpHex("#F59E0B", "#EF4444", t);
          stroke = fill;
          textColor = "#0b1416";
        } else if (isCurrent) {
          fill = "#0EA5E9";
          stroke = "#00F2FF";
          textColor = "#0b1416";
        }

        return (
          <g key={label}>
            <circle
              cx={cx}
              cy={cy}
              r={isLatchStage ? 11 : 9}
              fill={fill}
              stroke={stroke}
              strokeWidth={isLatchStage ? 2 : 1.5}
              strokeDasharray={dashed ? "2 2" : undefined}
              className={isCurrent || isLatchStage ? "animate-stage-pulse" : undefined}
              style={{ transition: "fill 300ms ease, stroke 300ms ease" }}
            />
            {isLatchStage && (
              <text
                x={cx}
                y={cy + 3.5}
                textAnchor="middle"
                fontSize="11"
                fontWeight={700}
                fill="#fff"
              >
                ⛨
              </text>
            )}
            {!isLatchStage && predetected && stageIndex < s.predetectionStage! && (
              <text x={cx} y={cy + 3} textAnchor="middle" fontSize="9" fontWeight={700} fill="#0b1416">
                {stageIndex}
              </text>
            )}
            {isPrevented && (
              <text
                x={cx}
                y={cy + 3}
                textAnchor="middle"
                fontSize="9"
                fontWeight={700}
                fill="rgba(16,185,129,0.85)"
              >
                ✓
              </text>
            )}
            {/* Mid-chain mitigation gets a green check; post-detection
                gets the stage number on the amber→red gradient. */}
            {!predetected && s.mitigated && !s.completed && stageIndex <= reached && (
              <text x={cx} y={cy + 3} textAnchor="middle" fontSize="9" fontWeight={700} fill="#fff">
                ✓
              </text>
            )}
            {!predetected && (s.completed || !s.mitigated) && past && (
              <text x={cx} y={cy + 3} textAnchor="middle" fontSize="9" fontWeight={700} fill="#0b1416">
                {stageIndex}
              </text>
            )}
            <text
              x={cx}
              y={H - 2}
              textAnchor="middle"
              fontSize="8"
              fill={textColor}
              fontFamily="ui-monospace, SFMono-Regular, monospace"
            >
              {label}
            </text>
          </g>
        );
      })}

      {/* Forward fill marker at current node (for sub-cell progress hint). */}
      {!s.completed && !s.mitigated && current > 0 && (
        <line
          x1={fillEndX}
          y1={cy - 12}
          x2={fillEndX}
          y2={cy + 12}
          stroke="#00F2FF"
          strokeWidth={1.5}
          strokeDasharray="2 2"
          opacity={0.6}
        />
      )}
    </svg>
  );
}

// ---- Helpers ----------------------------------------------------------------

// "2.0s" / "58s" / "412ms" — keeps sub-second values legible without
// rounding away the agent's reaction speed.
function formatTtiLabel(ms: number): string {
  if (ms < 1000) return `${Math.max(1, Math.round(ms))}ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
}

function stageSeverity(stage: number) {
  if (stage >= 6) return "critical" as const;
  if (stage >= 4) return "high" as const;
  if (stage >= 2) return "medium" as const;
  if (stage >= 1) return "low" as const;
  return "benign" as const;
}

function lerpHex(from: string, to: string, t: number): string {
  const f = hexToRgb(from);
  const g = hexToRgb(to);
  const r = Math.round(f.r + (g.r - f.r) * t);
  const gC = Math.round(f.g + (g.g - f.g) * t);
  const b = Math.round(f.b + (g.b - f.b) * t);
  return `#${[r, gC, b].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const h = hex.replace("#", "");
  const n = parseInt(h, 16);
  return { r: (n >> 16) & 0xff, g: (n >> 8) & 0xff, b: n & 0xff };
}
