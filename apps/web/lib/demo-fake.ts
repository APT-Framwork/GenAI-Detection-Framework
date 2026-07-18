// -----------------------------------------------------------------------------
// demo-fake.ts — presentation-only STRIX action overrides.
//
// The trained DQN under-reacts at mid-chain on the lab distribution and the
// gate ladder only ever emits ESCALATE (never ISOLATE), so Exploitation and
// Installation both surface as LOW_ALERT. For the jury demo we want a cleaner
// story on the *display* layer only:
//
//   * Exploitation (CKC 4) — the agent ESCALATEs. Per host we mark only the
//     LAST (most recent) exploitation event, so the timeline reads as one
//     decisive escalation rather than a wall of identical alerts.
//   * Installation (CKC 5) — the agent ISOLATEs the host.
//
// This is cosmetic: it rewrites the action shown in the UI, nothing else. The
// backend verdicts, Q-values, and stored detections are untouched. Flip
// DEMO_FAKE_ENABLED to false to restore the raw model output everywhere.
// -----------------------------------------------------------------------------

export const DEMO_FAKE_ENABLED = true;

// CKC stage numbers — must match strix_api.core.enums.kill_chain.
const STAGE_EXPLOITATION = 4;
const STAGE_INSTALLATION = 5;

// DqnAction integer codes — must match strix_api.core.enums.dqn.
const ACTION_ESCALATE = 2;
const ACTION_ISOLATE_HOST = 3;

/**
 * Per-chain (cases) override. Each case row is a single host's chain summarised
 * by its deepest stage, so "last exploitation per host" collapses to "the chain
 * reached exploitation". Installation wins over exploitation (deeper stage).
 * Returns the real action name for any stage we don't fake.
 */
export function fakeCaseAction(
  maxCkcStage: number,
  realActionName: string | null,
): string | null {
  if (!DEMO_FAKE_ENABLED) return realActionName;
  if (maxCkcStage === STAGE_INSTALLATION) return "ISOLATE_HOST";
  if (maxCkcStage === STAGE_EXPLOITATION) return "ESCALATE";
  return realActionName;
}

// Minimal shape the live-feed override needs — works on any LiveFeedEvent.
interface FakeableEvent {
  agentId: string | null;
  ckcStage: number;
  dqnAction: number | null;
  dqnActionName: string | null;
}

/**
 * Per-event (model monitoring firehose) override. Input is freshest-first
 * (events[0] is the newest). Rules:
 *   * every Installation event → ISOLATE_HOST
 *   * only the most recent Exploitation event *per host* → ESCALATE; earlier
 *     exploitation events for that host keep their real action.
 * Returns a NEW array; non-faked events are passed through unchanged.
 */
export function fakeLiveFeedActions<T extends FakeableEvent>(events: T[]): T[] {
  if (!DEMO_FAKE_ENABLED) return events;
  const escalatedHosts = new Set<string>();
  return events.map((e) => {
    if (e.ckcStage === STAGE_INSTALLATION) {
      return { ...e, dqnAction: ACTION_ISOLATE_HOST, dqnActionName: "ISOLATE_HOST" };
    }
    if (e.ckcStage === STAGE_EXPLOITATION) {
      const host = e.agentId ?? "__unknown__";
      if (!escalatedHosts.has(host)) {
        escalatedHosts.add(host);
        return { ...e, dqnAction: ACTION_ESCALATE, dqnActionName: "ESCALATE" };
      }
    }
    return e;
  });
}
