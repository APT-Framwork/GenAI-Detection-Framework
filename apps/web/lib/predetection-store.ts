// -----------------------------------------------------------------------------
// predetection-store.ts — shared per-host predetection state.
//
// The RL kill-chain panel decides when a host is "predetected" (DQN action ≥
// ESCALATE while chain hasn't reached stage 7 yet). Several panels need to
// react to that fact:
//   * RlKillChain — freeze the row's stage progression + render the proof.
//   * SimulationTopologyPanel — stop the attacker→victim dot animation,
//     swap the edge to BLOCKED, paint a shield on the victim.
//   * PredetectionReceipt (inline + rail variants) — render the credibility
//     card.
//
// We keep this as a tiny module-level pub/sub instead of pulling in a state
// library: only the kill-chain writes, everyone else reads, the cardinality
// is bounded by the number of victim hosts (≤ a few dozen).
// -----------------------------------------------------------------------------

import { useEffect, useState } from "react";

export interface Predetection {
  hostId: string;
  victimLabel: string | null; // hostname or srcip — what we render
  /** Kill-chain stage at which the agent intervened (1..7). ≤ 6 = predetection success. */
  stage: number;
  /** stages 5–6 are the paper's "critical max" — catching at ≤ 4 is even better. */
  isCritical: boolean;
  /** Event-time TTI: gap between two Wazuh `occurred_at` timestamps —
   *  the alert that opened the chain and the alert that triggered ESCALATE.
   *  Tells you "how deep into the chain" the agent fired. Not affected by
   *  pipeline latency (both endpoints are event-time). */
  elapsedMs: number;
  /** Wall-clock TTI: server clock at decide-time minus server clock at
   *  chain-open. Captures end-to-end pipeline latency (Filebeat → OpenSearch
   *  → ingest → inference). May be null for backfilled/older sessions. */
  wallElapsedMs: number | null;
  /** Last MITRE technique observed before intervention (e.g., "T1059.004"). */
  technique: string | null;
  /** Last MITRE tactic observed before intervention (e.g., "TA0002"). */
  tactic: string | null;
  /** DQN action int + name — the agent's recommendation. */
  action: number;
  actionName: string;
  /** Transformer confidence at the moment of latch. */
  confidence: number;
  /** Wall-clock ms when the latch fired. */
  latchedAt: number;
}

type Store = Map<string, Predetection>;

// Pin the store + listener set to `globalThis` so they survive module
// re-evaluation. Without this, Next.js HMR can leave the page holding two
// copies of this module (e.g. rl-kill-chain ends up bound to a fresh module
// after edit, while predetection-receipt is still bound to the original).
// The two modules each have their own `_store`, so writes on one side are
// invisible to the other — symptom: the RL timeline shows N predetected
// rows while the receipt panel renders the empty "Awaiting predetection"
// state. Anchoring on globalThis collapses both instances onto a single Map.
interface PredetectionGlobal {
  __strixPredetectionStore?: Store;
  __strixPredetectionListeners?: Set<() => void>;
}
const _g = globalThis as unknown as PredetectionGlobal;
const _store: Store = (_g.__strixPredetectionStore ??= new Map());
const _listeners: Set<() => void> = (_g.__strixPredetectionListeners ??= new Set());

function _emit(): void {
  _listeners.forEach((fn) => fn());
}

export function recordPredetection(p: Predetection): void {
  // Latch: do not overwrite an already-predetected host. The first
  // intervention is the truth; subsequent RL frames for the same host
  // are noise from the attacker continuing to thrash before it notices
  // the chain has been frozen client-side.
  if (_store.has(p.hostId)) return;
  _store.set(p.hostId, p);
  _emit();
}

export function clearPredetection(hostId: string): void {
  if (_store.delete(hostId)) _emit();
}

export function clearAllPredetections(): void {
  if (_store.size === 0) return;
  _store.clear();
  _emit();
}

export function getPredetection(hostId: string): Predetection | undefined {
  return _store.get(hostId);
}

/** React subscription — re-renders the consumer on any store mutation.
 *
 * Returns a NEW Map snapshot each render so downstream `useMemo([map], ...)`
 * actually invalidates when entries change. Returning the raw module-level
 * `_store` looks tidy but the reference never changes, which makes memoised
 * derivations (e.g. `useMemo(() => Array.from(all.values()), [all])`)
 * permanently stale even though the component re-renders on each `_emit`.
 * The snapshot is shallow (Predetection objects are themselves frozen-ish);
 * cardinality is bounded by victim count, so the per-render copy is cheap. */
export function usePredetections(): ReadonlyMap<string, Predetection> {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick((n) => n + 1);
    _listeners.add(fn);
    return () => {
      _listeners.delete(fn);
    };
  }, []);
  // Fresh snapshot on every render-after-emit. Identity changes ⇒ memos
  // tied to this map dep actually re-compute.
  return new Map(_store);
}

export function usePredetection(hostId: string | null | undefined): Predetection | undefined {
  const all = usePredetections();
  return hostId ? all.get(hostId) : undefined;
}
