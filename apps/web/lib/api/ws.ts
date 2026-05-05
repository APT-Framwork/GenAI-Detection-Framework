// -----------------------------------------------------------------------------
// ws.ts — singleton WebSocket client for /api/v1/logs/stream (Phase 3).
//
// Backend envelope (apps/api/src/strix_api/api/routes/streams.py):
//   { type: "raw_log"|"ae"|"vae"|"gnn"|"rl"|"topology"|"status",
//     ts: ISO-8601,
//     payload: { ... } }
//
// Design:
//   * One WebSocket per browser tab. All consumers share it via subscribe().
//   * Auto-reconnect with capped exponential backoff (500ms → 30s).
//   * Per-type bounded ring buffer (default cap 500) keeps memory flat over
//     long sessions. The `useLogStream` hook re-renders subscribers via a
//     monotonic seq counter, not by passing the buffer reference itself, so
//     consumers can opt into the data they need (slice or last-N).
//   * No external deps — pure browser WebSocket + React.
// -----------------------------------------------------------------------------

"use client";

import { useEffect, useRef, useState } from "react";

// ---- Envelope types ---------------------------------------------------------

export type FrameType =
  | "raw_log"
  | "ae"
  | "vae"
  | "gnn"
  | "rl"
  | "topology"
  | "status";

export interface BaseFrame<T extends FrameType, P> {
  type: T;
  ts: string;
  payload: P;
}

export interface RawLogPayload {
  // Matches `build_live_feed_event` in apps/api/src/strix_api/services/live_feed.py.
  alertId?: string;
  agentId?: string | null;
  chainId?: string | null;
  occurredAt?: string;
  ckcStage?: number;
  ckcStageName?: string;
  vaeMaliciousProb?: number | null;
  aeAnomalyScore?: number | null;
  gnnNodeRisk?: number | null;
  dqnAction?: number | null;
  dqnActionName?: string | null;
  mitreTechniques?: string[];
  // Permissive extras for compatibility with raw Wazuh-style payloads.
  alert_id?: string;
  agent_id?: string | null;
  rule_id?: number | string | null;
  description?: string;
  full_log?: string;
  srcip?: string | null;
  src_ip?: string | null;
  synthetic_benign?: boolean;
  tags?: Record<string, unknown>;
  [k: string]: unknown;
}

export interface AePayload {
  alert_id?: string;
  host_id?: string | null;
  srcip?: string | null;
  recon_error?: number;
  anomaly_score?: number;
  label?: Label;
  mitre_tactics?: string[];
  mitre_techniques?: string[];
  [k: string]: unknown;
}

export interface VaePayload {
  alert_id?: string;
  host_id?: string | null;
  srcip?: string | null;
  malicious_prob?: number;
  uncertainty?: number;
  label?: Label;
  mitre_tactics?: string[];
  mitre_techniques?: string[];
  [k: string]: unknown;
}

export interface GnnPayload {
  alert_id?: string;
  agent_id?: string | null;
  // Backend (apps/api/.../inference.py STREAM_GNN_CHANNEL fan-out) emits these.
  host_id?: string | null;
  srcip?: string | null;
  node_risk?: number;
  neighbor_risk?: number;
  risk_growth?: number;
  affected_edges?: number;
  cluster_id?: string | number | null;
  label?: Label;
  [k: string]: unknown;
}

export interface RlPayload {
  alert_id?: string;
  host_id?: string | null;
  agent_id?: string | null;
  srcip?: string | null;
  action?: number;
  action_name?: string;
  q_values?: number[];
  // ckc_stage is the *display* value chosen by the backend — usually the max
  // of the three stage signals below — so older readers stay sane.
  ckc_stage?: number;
  transformer_pred_ckc?: number;
  mitre_ckc_stage?: number;
  chain_max_ckc_stage?: number;
  confidence?: number;
  mitre_tactics?: string[];
  mitre_techniques?: string[];
  // Backend-authoritative timing for the RL Intervention Timeline. Both
  // ISO timestamps come from Wazuh occurred_at, so the dashboard can show
  // a true time-to-intervene without relying on browser-side `Date.now()`.
  chain_opened_at?: string | null;
  event_occurred_at?: string | null;
  time_to_intervene_ms?: number | null;
  // Wall-clock TTI — server clock at decide-time minus server clock at
  // chain-open. Captures end-to-end pipeline latency (Filebeat → OpenSearch
  // → ingest → inference) which the event-time `time_to_intervene_ms`
  // collapses to ~zero on Caldera bursts. Pair both in the UI for the
  // "two stories" view: how-deep-into-the-chain vs. real wall-clock.
  wall_time_to_intervene_ms?: number | null;
  [k: string]: unknown;
}

export interface TopologyVictim {
  ip?: string;
  hostname?: string;
  name?: string;
  agents?: string[];
  agent_id?: string | null;
}

export interface TopologyPayload {
  run_id?: string;
  started_at?: string;
  attacker_ip?: string;
  apt_group?: string;
  apt?: string;
  tactics_planned?: string[];
  victims?: TopologyVictim[];
  [k: string]: unknown;
}

export interface StatusPayload {
  state: "connected" | "heartbeat" | "shutdown" | string; // "dropped:N" runtime-tagged
  [k: string]: unknown;
}

export type Label = "tp" | "fp" | "tn" | "fn" | "unknown";

export type Envelope =
  | BaseFrame<"raw_log", RawLogPayload>
  | BaseFrame<"ae", AePayload>
  | BaseFrame<"vae", VaePayload>
  | BaseFrame<"gnn", GnnPayload>
  | BaseFrame<"rl", RlPayload>
  | BaseFrame<"topology", TopologyPayload>
  | BaseFrame<"status", StatusPayload>;

export type EnvelopeOf<T extends FrameType> = Extract<Envelope, { type: T }>;

// ---- Connection state -------------------------------------------------------

export type ConnectionState = "connecting" | "open" | "reconnecting" | "offline";

// ---- URL resolution ---------------------------------------------------------

const API_BASE: string =
  (process.env.NEXT_PUBLIC_STRIX_API_BASE ?? "/api/v1").replace(/\/$/, "");

function resolveWsUrl(): string {
  // Override for tests / non-browser env.
  const override = process.env.NEXT_PUBLIC_STRIX_WS_URL;
  if (override) return override.replace(/\/$/, "") + "/logs/stream";

  if (typeof window === "undefined") {
    return "ws://localhost/api/v1/logs/stream"; // SSR placeholder; ws never opens server-side
  }

  let base = API_BASE;
  // If API_BASE is absolute (http(s)://…) swap scheme. If relative, anchor on window.
  if (/^https?:\/\//i.test(base)) {
    base = base.replace(/^http/i, "ws");
  } else {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    base = `${proto}//${window.location.host}${base}`;
  }
  return `${base}/logs/stream`;
}

// ---- Singleton client -------------------------------------------------------

const DEFAULT_CAP = 500;

type Listener = () => void;

class LogStreamClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;
  private refCount = 0;

  private buffers: Map<FrameType, Envelope[]> = new Map();
  private seqByType: Map<FrameType, number> = new Map();
  private listenersByType: Map<FrameType, Set<Listener>> = new Map();

  private state: ConnectionState = "offline";
  private lastEventAt: number | null = null;
  private droppedTotal = 0;
  private connSeq = 0;
  private connListeners: Set<Listener> = new Set();

  private cap = DEFAULT_CAP;

  setCap(cap: number) {
    this.cap = Math.max(1, cap);
  }

  // ---- Public API ----------------------------------------------------------

  acquire() {
    this.refCount += 1;
    if (this.refCount === 1) this.connect();
  }

  release() {
    this.refCount = Math.max(0, this.refCount - 1);
    // Keep the socket open even at refCount 0 — connection-status-bar should
    // remain reflecting reality even with no panel mounted. The page unload
    // tears down the WebSocket naturally.
  }

  getState(): ConnectionState {
    return this.state;
  }

  getLastEventAt(): number | null {
    return this.lastEventAt;
  }

  getDroppedTotal(): number {
    return this.droppedTotal;
  }

  getBuffer<T extends FrameType>(type: T): ReadonlyArray<EnvelopeOf<T>> {
    return (this.buffers.get(type) ?? []) as unknown as ReadonlyArray<EnvelopeOf<T>>;
  }

  getSeq(type: FrameType): number {
    return this.seqByType.get(type) ?? 0;
  }

  subscribe(type: FrameType, listener: Listener): () => void {
    let set = this.listenersByType.get(type);
    if (!set) {
      set = new Set();
      this.listenersByType.set(type, set);
    }
    set.add(listener);
    return () => {
      set!.delete(listener);
    };
  }

  subscribeConnection(listener: Listener): () => void {
    this.connListeners.add(listener);
    return () => {
      this.connListeners.delete(listener);
    };
  }

  // ---- Internals -----------------------------------------------------------

  private setState(next: ConnectionState) {
    if (this.state === next) return;
    this.state = next;
    this.connSeq += 1;
    this.connListeners.forEach((l) => l());
  }

  private connect() {
    if (this.destroyed) return;
    if (typeof window === "undefined") return;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.setState(this.reconnectAttempts === 0 ? "connecting" : "reconnecting");
    let ws: WebSocket;
    try {
      ws = new WebSocket(resolveWsUrl());
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.setState("open");
    };

    ws.onmessage = (ev: MessageEvent<string>) => {
      this.handleFrame(ev.data);
    };

    ws.onerror = () => {
      // onerror always followed by onclose — handle teardown there.
    };

    ws.onclose = () => {
      this.ws = null;
      if (this.destroyed) return;
      this.scheduleReconnect();
    };
  }

  private handleFrame(raw: string) {
    let frame: Envelope;
    try {
      frame = JSON.parse(raw) as Envelope;
    } catch {
      return;
    }
    if (!frame || typeof frame !== "object" || typeof frame.type !== "string") return;

    this.lastEventAt = Date.now();

    if (frame.type === "status") {
      const state = (frame.payload as StatusPayload | undefined)?.state ?? "";
      if (typeof state === "string" && state.startsWith("dropped:")) {
        const n = parseInt(state.slice("dropped:".length), 10);
        if (Number.isFinite(n)) this.droppedTotal += n;
      }
      // Status frames flow into the buffer too — the status-bar renders the
      // freshest one for diagnostics.
    }

    const buf = this.buffers.get(frame.type) ?? [];
    buf.push(frame);
    if (buf.length > this.cap) buf.splice(0, buf.length - this.cap);
    this.buffers.set(frame.type, buf);

    const seq = (this.seqByType.get(frame.type) ?? 0) + 1;
    this.seqByType.set(frame.type, seq);

    const set = this.listenersByType.get(frame.type);
    if (set && set.size) set.forEach((l) => l());

    // Mirror non-status frames into a wildcard so the status-bar can refresh
    // its "last event" timestamp without subscribing to every type.
    if (frame.type !== "status") {
      this.connListeners.forEach((l) => l());
    }
  }

  private scheduleReconnect() {
    if (this.destroyed) return;
    this.setState("reconnecting");
    const delay = Math.min(30_000, 500 * 2 ** this.reconnectAttempts);
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      // Promote to "offline" if we've been retrying for a while.
      if (this.reconnectAttempts >= 4) this.setState("offline");
      this.connect();
    }, delay);
  }
}

let _singleton: LogStreamClient | null = null;
function getClient(): LogStreamClient {
  if (!_singleton) _singleton = new LogStreamClient();
  return _singleton;
}

// ---- React hooks ------------------------------------------------------------

/**
 * Subscribe to one or more frame types. Returns the latest snapshot of each
 * type's ring buffer plus a monotonically increasing seq counter (use it as a
 * memo key to derive expensive views).
 *
 * Safe to call from many components: all share the same singleton WebSocket.
 */
export function useLogStream<T extends FrameType>(
  types: ReadonlyArray<T>,
): {
  frames: { [K in T]: ReadonlyArray<EnvelopeOf<K>> };
  seq: { [K in T]: number };
} {
  const client = getClient();
  // Stable key for the type list — caller usually passes a literal array, but
  // useEffect deps need a primitive.
  const typesKey = types.slice().sort().join("|");

  const [, setTick] = useState(0);
  const tickRef = useRef(0);

  useEffect(() => {
    client.acquire();
    const unsubs = types.map((t) =>
      client.subscribe(t, () => {
        tickRef.current += 1;
        setTick(tickRef.current);
      }),
    );
    return () => {
      unsubs.forEach((u) => u());
      client.release();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typesKey]);

  const frames = {} as { [K in T]: ReadonlyArray<EnvelopeOf<K>> };
  const seq = {} as { [K in T]: number };
  for (const t of types) {
    frames[t] = client.getBuffer(t);
    seq[t] = client.getSeq(t);
  }
  return { frames, seq };
}

/** Live connection state + last-event timestamp for the status bar. */
export function useLogStreamConnection(): {
  state: ConnectionState;
  lastEventAt: number | null;
  droppedTotal: number;
} {
  const client = getClient();
  const [, setTick] = useState(0);

  useEffect(() => {
    client.acquire();
    const unsub = client.subscribeConnection(() => setTick((n) => n + 1));
    return () => {
      unsub();
      client.release();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    state: client.getState(),
    lastEventAt: client.getLastEventAt(),
    droppedTotal: client.getDroppedTotal(),
  };
}

// Test-only: reset singleton between unit tests.
export function __resetLogStreamForTests() {
  _singleton = null;
}
