// -----------------------------------------------------------------------------
// apt-attack-timeline.tsx — LIVE attacker progression, paced.
//
// Sister panel to rl-kill-chain.tsx (RL Intervention Timeline). Shows the
// attacker walking through the 7 CKC stages in real time but at a humanly
// readable cadence: each stage holds for a minimum of MIN_STAGE_DWELL_MS
// before the visual is allowed to advance, even if real events arrive
// faster. Mimics the way an APT actually unfolds (Recon doesn't complete
// in 200 ms) without coupling the dashboard to Caldera's orchestrator.
//
// A session disappears from this panel when it reaches a terminal state:
//   * predetected (via predetection-store) — the RL agent intervened
//   * reached stage 7 (chain completed)
// In both cases the frozen-final card shows up in the RL Intervention
// Timeline panel next door.
//
// The visual contract: ANY session shown here is "live attack in progress."
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { useLogStream, type RlPayload } from "@/lib/api/ws";
import { usePredetections } from "@/lib/predetection-store";

const STAGE_LABELS = [
  "Recon",
  "Weapon",
  "Delivery",
  "Exploit",
  "Install",
  "C2",
  "Action",
] as const;

// Minimum visual dwell on each stage before the timeline is allowed to
// advance to the next, regardless of how fast real events arrive. 6 s is
// long enough to read the stage label + mentally register progression,
// short enough that a 7-stage chain still completes in ~45 s of UI time.
const MIN_STAGE_DWELL_MS = 6000;

// When the real chain has run far ahead of what we're showing (Caldera
// can blast through all 7 stages in well under a second), the 6 s/stage
// pacing leaves the APT panel showing "Recon" for ~40 s while the RL
// Intervention Timeline next door is already showing POST-DETECTION
// at Action. That mismatch is what the user actually perceives as a
// bug. So when there's a backlog, shrink the dwell proportionally —
// the deeper the backlog, the faster the catch-up — so the visual
// always converges to truth within a few seconds.
const CATCHUP_FAST_DWELL_MS = 700;
// Backlog depth (observedMaxStage − pacedStage) at which we switch
// from the readable 6 s pacing to the fast catch-up cadence. Below
// this we still pace nicely so a slow attack feels deliberate.
const BACKLOG_FAST_THRESHOLD = 2;

// Inactivity timeout: drop a session if no new RL frame for this host in
// this window AND it hasn't reached stage 7 / been predetected. Keeps the
// panel clean if a chain stalls mid-walk.
const SESSION_IDLE_MS = 60_000;

const MAX_VISIBLE_ROWS = 6;

interface PacedSession {
  hostId: string;
  srcip: string | null;
  /** What the data says the chain has actually reached. Monotonic. */
  observedMaxStage: number;
  /** What the UI is currently showing. Lags `observedMaxStage` by dwell. */
  pacedStage: number;
  /** Wall-clock ms when `pacedStage` last incremented. */
  lastAdvanceAt: number;
  /** Wall-clock ms when the latest RL frame arrived for this host. */
  lastFrameAt: number;
  startedAt: number;
  lastTechnique: string | null;
  lastTactic: string | null;
}

function numOr(v: unknown, fallback: number): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

function pickHost(p: RlPayload): string | null {
  return (
    (typeof p.host_id === "string" && p.host_id) ||
    (typeof p.srcip === "string" && p.srcip) ||
    (typeof p.agent_id === "string" && p.agent_id) ||
    null
  );
}

interface AptAttackTimelineProps {
  className?: string;
}

export function AptAttackTimeline({ className }: AptAttackTimelineProps) {
  const stream = useLogStream(["rl"]);
  const seq = stream.seq.rl;
  const predetections = usePredetections();

  const sessionsRef = useRef<Map<string, PacedSession>>(new Map());
  const lastSeqRef = useRef(0);
  const [, setTick] = useState(0);

  // Drain RL frames into per-host observed-stage map.
  //
  // CRITICAL: a session is only OPENED for a host once we see an RL frame
  // with non-trivial signal — i.e. a CKC stage > 0 or a MITRE tag. Pure
  // benign auditd noise (rule 80789, no MITRE tag, stage = 0) does NOT
  // populate this panel; it's a kill-chain timeline, not a generic event
  // monitor. If the only traffic is benign, the panel says "no active
  // kill chain" and stays clean.
  //
  // Once a session IS opened, subsequent frames for that host update
  // observedMaxStage even at stage 0 (so we don't idle-evict during a
  // burst of benign noise interleaved with attack tactics — the user
  // wants to see the attack continue, not have the row vanish during
  // the lulls between Caldera tactics).
  useEffect(() => {
    if (seq <= lastSeqRef.current) return;
    const buf = stream.frames.rl;
    const fresh = buf.slice(buf.length - (seq - lastSeqRef.current));
    lastSeqRef.current = seq;

    const now = Date.now();
    const map = sessionsRef.current;

    for (const env of fresh) {
      const p = env.payload;
      const id = pickHost(p);
      if (!id) continue;

      // Maximum stage signal across the four available channels.
      const stage = Math.max(
        numOr(p.transformer_pred_ckc, 0),
        numOr(p.mitre_ckc_stage, 0),
        numOr(p.chain_max_ckc_stage, 0),
        numOr(p.ckc_stage, 0),
      );

      const tactics = Array.isArray(p.mitre_tactics) ? p.mitre_tactics : [];
      const techniques = Array.isArray(p.mitre_techniques) ? p.mitre_techniques : [];
      const lastTechnique =
        techniques.length > 0 ? techniques[techniques.length - 1] : null;
      const lastTactic = tactics.length > 0 ? tactics[tactics.length - 1] : null;

      const existing = map.get(id);
      const isMaliciousFrame = stage > 0 || tactics.length > 0 || techniques.length > 0;

      // Gate session creation on a malicious-looking frame. Pure benign
      // noise from a host we haven't seen before is dropped entirely.
      if (!existing && !isMaliciousFrame) continue;

      // If this host has been predetected, the RL Intervention Timeline
      // panel owns it. Skip in the drain too — otherwise the drain
      // re-adds the session faster than the 1 Hz tick can evict it,
      // making the row flicker visible. The store is keyed by host
      // not chain, so a brand-new chain on the same host stays hidden
      // here until the user clears predetections (acceptable for v1).
      if (predetections.has(id)) continue;

      const observedMaxStage = Math.max(existing?.observedMaxStage ?? 0, stage);

      map.set(id, {
        hostId: id,
        srcip: (typeof p.srcip === "string" ? p.srcip : existing?.srcip) ?? null,
        observedMaxStage,
        // pacedStage is left untouched here — only the tick loop advances
        // it. New session starts at stage 0 visually and walks up.
        pacedStage: existing?.pacedStage ?? 0,
        lastAdvanceAt: existing?.lastAdvanceAt ?? now,
        lastFrameAt: now,
        startedAt: existing?.startedAt ?? now,
        lastTechnique: lastTechnique ?? existing?.lastTechnique ?? null,
        lastTactic: lastTactic ?? existing?.lastTactic ?? null,
      });
    }
    setTick((n) => n + 1);
    // predetections is included so the drain re-binds when a new
    // host gets latched — otherwise the closure carries a stale Map
    // and the predetection-skip check misses freshly-latched hosts.
  }, [seq, stream.frames.rl, predetections]);

  // 1 Hz tick: advance pacedStage toward observedMaxStage at dwell speed,
  // and evict idle / terminal sessions.
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      const map = sessionsRef.current;
      const toDelete: string[] = [];

      map.forEach((s, id) => {
        // Evict if predetected (the RL Intervention Timeline owns it now).
        if (predetections.has(id)) {
          toDelete.push(id);
          return;
        }
        // Evict if reached stage 7 — chain is over, intervention panel
        // shows the post-detection.
        if (s.pacedStage >= 7) {
          toDelete.push(id);
          return;
        }
        // Evict if idle.
        if (now - s.lastFrameAt > SESSION_IDLE_MS) {
          toDelete.push(id);
          return;
        }
        // Maybe advance pacedStage. Use a shorter dwell when the real
        // chain has run far ahead of what's displayed, so the visual
        // converges to truth instead of getting stuck showing "Recon"
        // while the RL panel next door already declared POST-DETECTION.
        if (s.pacedStage < s.observedMaxStage) {
          const backlog = s.observedMaxStage - s.pacedStage;
          const dwell =
            backlog >= BACKLOG_FAST_THRESHOLD ? CATCHUP_FAST_DWELL_MS : MIN_STAGE_DWELL_MS;
          if (now - s.lastAdvanceAt >= dwell) {
            s.pacedStage += 1;
            s.lastAdvanceAt = now;
          }
        }
      });

      for (const id of toDelete) map.delete(id);
      setTick((n) => n + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [predetections]);

  const sessions = useMemo(() => {
    return Array.from(sessionsRef.current.values()).sort(
      (a, b) => b.lastFrameAt - a.lastFrameAt,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seq, sessionsRef.current.size, predetections.size]);

  const visible = sessions.slice(0, MAX_VISIBLE_ROWS);
  const overflow = Math.max(0, sessions.length - visible.length);

  return (
    <div className={cn("w-full", className)}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-bold font-heading text-[#00343d] dark:text-[var(--strix-text)]">
            APT Attack Timeline
          </h3>
          <p className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-0.5">
            live attacker progression — paced 6 s/stage
          </p>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {sessions.length} active
        </span>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[rgba(128,182,195,0.25)] dark:border-[var(--strix-border)] py-8 text-center">
          <div className="inline-flex items-center gap-2 text-emerald-600/80 dark:text-emerald-400/80 text-[11px] font-mono uppercase tracking-wider">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            no active kill chain
          </div>
          <p className="text-[9px] text-[#497f8b] dark:text-[var(--strix-text-muted)] mt-2">
            timeline idles when traffic is benign — rows appear when a host
            emits a MITRE-tagged event
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {visible.map((s) => (
            <AttackRow key={s.hostId} session={s} />
          ))}
        </div>
      )}

      {overflow > 0 && (
        <div className="mt-3 text-center text-[10px] uppercase tracking-wider text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          + {overflow} more session{overflow === 1 ? "" : "s"}
        </div>
      )}
    </div>
  );
}

function AttackRow({ session: s }: { session: PacedSession }) {
  const elapsedSec = Math.max(0, Math.round((Date.now() - s.startedAt) / 1000));
  const stageLabel = s.pacedStage > 0 ? STAGE_LABELS[s.pacedStage - 1] : "—";
  const aheadOfPace = s.observedMaxStage - s.pacedStage; // backlog (data has reached deeper)

  return (
    <div className="rounded-xl border border-rose-500/30 bg-[var(--strix-bg-card)] dark:bg-[var(--strix-bg-surface)] p-3 animate-slide-up-in">
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] font-mono font-bold text-[#00343d] dark:text-[var(--strix-text)] truncate">
            {s.hostId}
          </span>
          <span className="text-[9px] font-mono text-rose-500 font-semibold">
            ▶ {stageLabel}
          </span>
          {aheadOfPace > 0 && (
            <span
              className="text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]"
              title="real chain is deeper than the displayed stage; UI is catching up at 6s/stage"
            >
              (+{aheadOfPace} pending)
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0 text-[9px] font-mono text-[#497f8b] dark:text-[var(--strix-text-muted)]">
          {s.lastTechnique && (
            <span className="text-[#00343d] dark:text-[var(--strix-text)]">
              {s.lastTechnique}
            </span>
          )}
          <span>{elapsedSec}s</span>
        </div>
      </div>

      <AttackStages stage={s.pacedStage} />
    </div>
  );
}

/** Live attacker progress — past stages amber→red gradient, current stage
    pulses cyan, future stages ghost gray. No mitigation overlays here:
    this panel deliberately shows the attacker's view, not the agent's. */
function AttackStages({ stage }: { stage: number }) {
  const W = 560;
  const H = 44;
  const padX = 16;
  const slotW = (W - 2 * padX) / (STAGE_LABELS.length - 1);
  const cy = H / 2;
  const reached = Math.max(0, Math.min(7, stage));

  return (
    <svg
      className="w-full"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="APT attack progression"
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
      {/* Progress fill — attacker's reach */}
      {reached > 0 && (
        <line
          x1={padX}
          y1={cy}
          x2={padX + Math.max(0, reached - 1) * slotW}
          y2={cy}
          stroke="#EF4444"
          strokeWidth={3}
          strokeLinecap="round"
          style={{ transition: "x2 600ms ease" }}
        />
      )}

      {STAGE_LABELS.map((label, i) => {
        const stageIdx = i + 1;
        const cx = padX + i * slotW;
        const past = stageIdx < reached;
        const isCurrent = stageIdx === reached && reached > 0;
        const future = stageIdx > reached;

        let fill = "rgba(128,182,195,0.18)";
        let stroke = "rgba(128,182,195,0.45)";
        let textColor = "#497f8b";
        if (past) {
          // amber→red gradient by depth
          const t = stageIdx / 7;
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
              r={9}
              fill={fill}
              stroke={stroke}
              strokeWidth={1.5}
              className={isCurrent ? "animate-stage-pulse" : undefined}
              style={{ transition: "fill 400ms ease, stroke 400ms ease" }}
            />
            {past && (
              <text
                x={cx}
                y={cy + 3}
                textAnchor="middle"
                fontSize="9"
                fontWeight={700}
                fill="#0b1416"
              >
                {stageIdx}
              </text>
            )}
            {!past && !future && isCurrent && (
              <text
                x={cx}
                y={cy + 3}
                textAnchor="middle"
                fontSize="9"
                fontWeight={700}
                fill="#fff"
              >
                {stageIdx}
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
    </svg>
  );
}

// ---- Helpers ----------------------------------------------------------------

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
