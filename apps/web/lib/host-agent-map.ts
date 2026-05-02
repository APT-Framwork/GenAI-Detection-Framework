// -----------------------------------------------------------------------------
// host-agent-map.ts — runtime hostname ↔ agent_id mapping.
//
// topology.json carries victims by hostname/ip; live frames key by agent_id.
// Without a join key the dashboard ends up labelling the same host twice
// (once as "victim1", once as "007"). We learn the join at runtime from the
// raw_log stream — those frames carry BOTH agent_id and srcip, and the
// topology panel already resolves srcip → hostname when it routes pulses.
// We piggy-back on that work and expose a tiny pub-sub the GNN panel and
// topology panel can read.
// -----------------------------------------------------------------------------

import { useEffect, useState } from "react";

const _agentToHost = new Map<string, string>(); // agent_id → hostname
const _hostToAgent = new Map<string, string>(); // hostname → agent_id
const _listeners = new Set<() => void>();

function _emit(): void {
  _listeners.forEach((fn) => fn());
}

export function recordHostAgent(agentId: string | null | undefined, hostname: string | null | undefined): void {
  if (!agentId || !hostname) return;
  if (_agentToHost.get(agentId) === hostname && _hostToAgent.get(hostname) === agentId) return;
  _agentToHost.set(agentId, hostname);
  _hostToAgent.set(hostname, agentId);
  _emit();
}

export function getAgentForHost(hostname: string | null | undefined): string | undefined {
  return hostname ? _hostToAgent.get(hostname) : undefined;
}

export function getHostForAgent(agentId: string | null | undefined): string | undefined {
  return agentId ? _agentToHost.get(agentId) : undefined;
}

/** React subscription. Returns a fresh snapshot each emit so memos invalidate. */
export function useHostAgentMap(): {
  agentToHost: ReadonlyMap<string, string>;
  hostToAgent: ReadonlyMap<string, string>;
} {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick((n) => n + 1);
    _listeners.add(fn);
    return () => {
      _listeners.delete(fn);
    };
  }, []);
  return {
    agentToHost: new Map(_agentToHost),
    hostToAgent: new Map(_hostToAgent),
  };
}
